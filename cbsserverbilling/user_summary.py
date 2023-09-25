"""Run the billing script."""

from __future__ import annotations

import argparse
import datetime
import itertools
from os import PathLike

import pandas as pd

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
    parser.add_argument("pi_form", type=str, help="path to the PI form data")
    parser.add_argument(
        "pi_update_form",
        type=str,
        help="path to the storage update form data",
    )
    parser.add_argument("user_form", type=str, help="path to the user form data")
    parser.add_argument(
        "user_update_form",
        type=str,
        help="path to the user update form data",
    )
    parser.add_argument(
        "start_date_iso",
        type=str,
        help="first day of the period to count users",
    )
    parser.add_argument(
        "end_date_iso",
        type=str,
        help="last day of the period to count users",
    )
    parser.add_argument(
        "out_path",
        type=str,
        help="file into which to user CSV",
    )

    return parser


def count_users(  # noqa: PLR0913
    pi_form: PathLike[str] | str,
    user_form: PathLike[str] | str,
    user_update_form: PathLike[str] | str,
    pi_update_form: PathLike[str] | str,
    start_date_iso: str,
    end_date_iso: str,
    out_path: PathLike[str] | str,
) -> None:
    """Generate all bills and a summary."""
    pi_df = load_pi_df(pi_form)
    user_df = load_user_df(user_form)
    user_update_df = load_user_update_df(user_update_form)
    pi_update_df = load_storage_update_df(pi_update_form)

    start_date = datetime.date.fromisoformat(start_date_iso)
    end_date = datetime.date.fromisoformat(end_date_iso)
    records = gen_all_project_records(
        user_df,
        user_update_df,
        pi_df,
        pi_update_df,
        start_date,
        end_date,
    )
    users = itertools.chain.from_iterable(
        [record.enumerate_power_users(start_date, end_date) for record in records],
    )
    pd.DataFrame([{"name": user.name, "email": user.email} for user in users]).to_csv(
        out_path, index=False,
    )


def main() -> None:
    """Count users based on the CLI."""
    args = gen_parser().parse_args()
    count_users(
        args.pi_form,
        args.user_form,
        args.user_update_form,
        args.pi_update_form,
        args.start_date_iso,
        args.end_date_iso,
        args.out_path,
    )


if __name__ == "__main__":
    main()
