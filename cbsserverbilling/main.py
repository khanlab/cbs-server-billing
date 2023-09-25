"""Run the billing script."""

import argparse
import datetime
from os import PathLike
from pathlib import Path

from cbsserverbilling.billing import generate_all_pi_bills, summarize_all_pi_bills
from cbsserverbilling.dateutils import get_end_of_period
from cbsserverbilling.policy import BillingPolicy
from cbsserverbilling.spreadsheet.io import (
    load_pi_df,
    load_storage_update_df,
    load_user_df,
    load_user_update_df,
)
from cbsserverbilling.spreadsheet.record import gen_all_project_records


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

    return parser


def process_everything(  # noqa: PLR0913
    pi_form: PathLike[str] | str,
    user_form: PathLike[str] | str,
    user_update_form: PathLike[str] | str,
    pi_update_form: PathLike[str] | str,
    quarter_start_iso: str,
    out_dir: PathLike[str] | str,
) -> None:
    """Generate all bills and a summary."""
    pi_df = load_pi_df(pi_form)
    user_df = load_user_df(user_form)
    user_update_df = load_user_update_df(user_update_form)
    pi_update_df = load_storage_update_df(pi_update_form)

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


def main() -> None:
    """Generate and summarize all bills base on the CLI."""
    args = gen_parser().parse_args()
    process_everything(
        args.pi_form,
        args.user_form,
        args.user_update_form,
        args.pi_update_form,
        args.quarter_start,
        args.out_dir,
    )


if __name__ == "__main__":
    main()
