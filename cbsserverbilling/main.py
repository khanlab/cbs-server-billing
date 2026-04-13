"""Run the billing script."""

from __future__ import annotations

import argparse
import datetime
import logging
from os import PathLike
from pathlib import Path

import pandas as pd

from cbsserverbilling.billing import generate_all_pi_bills, summarize_all_pi_bills
from cbsserverbilling.dateutils import get_end_of_period
from cbsserverbilling.policy import BillingPolicy
from cbsserverbilling.snapshot import write_quarantine, write_snapshots
from cbsserverbilling.spreadsheet.io import (
    ingest_pi_df,
    ingest_storage_update_df,
    ingest_user_df,
    ingest_user_update_df,
)
from cbsserverbilling.spreadsheet.project import gen_all_projects
from cbsserverbilling.spreadsheet.record import gen_all_project_records
from cbsserverbilling.spreadsheet.user import enumerate_all_users
from cbsserverbilling.validation import (
    QUARANTINE_COL,
    validate_pi_update_refs,
    validate_power_user_pi_refs,
    validate_user_update_pi_refs,
    validate_user_update_refs,
)

logger = logging.getLogger(__name__)


def _concat_quarantines(
    *dfs: pd.DataFrame,
) -> pd.DataFrame:
    """Concatenate quarantine DataFrames, dropping any that are empty."""
    non_empty = [df for df in dfs if not df.empty]
    if not non_empty:
        # Return a proper empty DataFrame that has the QUARANTINE_COL column
        combined_cols = list({col for df in dfs for col in df.columns})
        if QUARANTINE_COL not in combined_cols:
            combined_cols.append(QUARANTINE_COL)
        return pd.DataFrame(columns=combined_cols)
    return pd.concat(non_empty, ignore_index=True)


def gen_parser() -> argparse.ArgumentParser:
    """Generate a command-line parser."""
    parser = argparse.ArgumentParser(description="Process CBS Server billing data.")
    parser.add_argument(
        "pi_form", type=str, help="Path to the PI account request form data",
    )
    parser.add_argument(
        "pi_update_form",
        type=str,
        help="Path to the PI/storage update form data",
    )
    parser.add_argument(
        "user_form", type=str, help="Path to the user account request form data",
    )
    parser.add_argument(
        "user_update_form",
        type=str,
        help="Path to the user update form data",
    )
    parser.add_argument(
        "quarter_start",
        type=str,
        help="First day of the quarter to bill",
    )
    parser.add_argument(
        "out_dir",
        type=str,
        help="Directory into which to output bill files",
    )
    parser.add_argument(
        "--no-quarantine",
        action="store_true",
        default=False,
        help="Disable quarantine: raise an error on any invalid input row instead",
    )

    return parser


def process_everything(  # noqa: PLR0913
    pi_form: PathLike[str] | str,
    user_form: PathLike[str] | str,
    user_update_form: PathLike[str] | str,
    pi_update_form: PathLike[str] | str,
    quarter_start_iso: str,
    out_dir: PathLike[str] | str,
    *,
    no_quarantine: bool = False,
) -> None:
    """Generate all bills, a summary, quarantine files, and snapshots.

    Parameters
    ----------
    pi_form
        Path to the PI account request spreadsheet.
    user_form
        Path to the user account request spreadsheet.
    user_update_form
        Path to the user update spreadsheet.
    pi_update_form
        Path to the PI/storage update spreadsheet.
    quarter_start_iso
        ISO-format date string for the first day of the billing quarter.
    out_dir
        Directory to write all output artefacts.
    no_quarantine
        When ``True``, raise an error on any invalid input row.  When
        ``False`` (default), invalid rows are written to quarantine CSV
        files and the pipeline continues with valid rows only.

    """
    # --- Ingest (load + validate + quarantine) ---
    pi_df, pi_quarantine = ingest_pi_df(pi_form)
    user_df, user_quarantine = ingest_user_df(user_form)
    user_update_df, user_update_quarantine = ingest_user_update_df(user_update_form)
    pi_update_df, pi_update_quarantine = ingest_storage_update_df(pi_update_form)

    # --- Cross-table reference validation ---
    # These checks prevent downstream domain errors that row-level validation
    # cannot catch on its own (e.g. InvalidPiUpdateError, InapplicableUpdateError,
    # UnattachedUserError).
    pi_update_df, pi_update_ref_quarantine = validate_pi_update_refs(
        pi_update_df, pi_df,
    )
    user_update_df, user_update_ref_quarantine = validate_user_update_refs(
        user_update_df, user_df,
    )
    # Quarantine update rows that set pi_last_name to a PI not in pi_form —
    # this prevents UnattachedUserError when a power user's PI is updated to
    # a non-existent value.
    user_update_df, user_update_pi_quarantine = validate_user_update_pi_refs(
        user_update_df, pi_df,
    )
    user_df, user_pi_ref_quarantine = validate_power_user_pi_refs(user_df, pi_df)

    quarantine_dfs = {
        "pi_form": pi_quarantine,
        "user_form": _concat_quarantines(user_quarantine, user_pi_ref_quarantine),
        "user_update_form": _concat_quarantines(
            user_update_quarantine,
            user_update_ref_quarantine,
            user_update_pi_quarantine,
        ),
        "storage_update_form": _concat_quarantines(
            pi_update_quarantine, pi_update_ref_quarantine,
        ),
    }
    total_quarantined = sum(len(q) for q in quarantine_dfs.values())

    if no_quarantine and total_quarantined > 0:
        for sheet, qdf in quarantine_dfs.items():
            if not qdf.empty:
                errors = qdf[QUARANTINE_COL].tolist()
                logger.error("Invalid rows in '%s':\n  %s", sheet, "\n  ".join(errors))
        msg = (
            f"{total_quarantined} invalid row(s) found in input sheets. "
            "Use the default mode (without --no-quarantine) to quarantine "
            "invalid rows and continue."
        )
        raise ValueError(msg)

    if total_quarantined > 0:
        write_quarantine(quarantine_dfs, out_dir)

    # --- Billing policy ---
    policy = BillingPolicy()
    start_date = datetime.date.fromisoformat(quarter_start_iso)
    end_date = get_end_of_period(
        start_date.year,
        start_date.month,
        policy.PERIOD_LENGTH,
    )

    records = gen_all_project_records(
        user_df,
        user_update_df,
        pi_df,
        pi_update_df,
        start_date,
        end_date,
    )
    summarize_all_pi_bills(
        records,
        start_date,
        Path(out_dir) / f"summary_{quarter_start_iso}.xlsx",
    )
    generate_all_pi_bills(records, start_date, out_dir)

    # --- Quarter-end snapshots ---
    projects, user_requests = gen_all_projects(
        pi_df,
        pi_update_df,
        start_date,
        end_date,
    )
    users = enumerate_all_users(
        user_df,
        user_update_df,
        start_date,
        end_date,
        additional_requests=user_requests,
    )
    write_snapshots(users, projects, end_date, out_dir)


def main() -> None:
    """Generate and summarize all bills based on the CLI."""
    args = gen_parser().parse_args()
    process_everything(
        args.pi_form,
        args.user_form,
        args.user_update_form,
        args.pi_update_form,
        args.quarter_start,
        args.out_dir,
        no_quarantine=args.no_quarantine,
    )


if __name__ == "__main__":
    main()
