"""Utilities to calculate CBS Server billing."""
from __future__ import annotations

import argparse
import datetime
import os
from pathlib import Path

import pandas as pd
from jinja2 import Environment, PackageLoader

from cbsserverbilling.policy import BillingPolicy
from cbsserverbilling.spreadsheet import PowerUsersRecord, StorageRecord

env = Environment(
    loader=PackageLoader("cbsserverbilling", "templates"), autoescape=True,
)


def load_user_df(user_form_path: os.PathLike) -> pd.DataFrame:
    """Load user Google Forms data into a usable pandas dataframe.

    Parameters
    ----------
    user_form_path : str
        Path to the excel sheet containing collected CBS server user data.

    Returns
    -------
    DataFrame
        A data frame with column names adjusted to be more usable, and the
        power user column cast to a boolean instead of a string.
    """
    user_df = pd.read_excel(user_form_path, engine="openpyxl")
    user_df = user_df.rename(
        columns={
            "Completion time": "start_timestamp",
            "Email": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "PI last name": "pi_last_name",
            "Contract end date": "end_timestamp",
            ("Do you need your account to be a Power User account"): "power_user",
        },
    )
    user_df = user_df.assign(power_user=user_df["power_user"].str.strip() == "Yes")
    return user_df


def load_user_update_df(user_update_form_path: os.PathLike) -> pd.DataFrame:
    """Load dataframe containing updates to user dataframe.

    Parameters
    ----------
    user_update_form_path : str
        Path to the user update form.

    Returns
    -------
    DataFrame
        Dataframe containing updates to user account specifications.
    """
    user_update_df = pd.read_excel(user_update_form_path, engine="openpyxl")
    user_update_df = user_update_df.rename(
        columns={
            "Completion time": "timestamp",
            "Email": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "PI Last name (e.g., Smith)": "pi_last_name",
            ("Request access to additional datashare "): "additional_datashare",
            ("Update contract end date"): "new_end_timestamp",
            "Change account type": "new_power_user",
            "List projects for which you need security access": "new_projects",
            ("Consent"): "agree",
            "Please feel free to leave any feedback": "feedback",
        },
    )
    user_update_df = user_update_df.assign(
        agree=user_update_df["agree"].str.strip() == "Yes",
        new_power_user=user_update_df["new_power_user"].map(
            lambda x: None if pd.isna(x) else x.strip() == "Power user",
        ),
    )
    return user_update_df


def load_pi_df(pi_form_path: os.PathLike) -> pd.DataFrame:
    """Load PI Google Forms data into a usable pandas dataframe.

    Parameters
    ----------
    pi_form_path
        Path to the PI form.
    """
    pi_df = pd.read_excel(pi_form_path, engine="openpyxl")
    pi_df = pi_df.rename(
        columns={
            "Completion time": "start_timestamp",
            "Email": "email",
            "First Name": "first_name",
            "Last Name": "last_name",
            (
                "Would you like your account to be a power user account?"
            ): "pi_is_power_user",
            "Speed code": "speed_code",
            "Required storage needs (in TB)": "storage",
        },
    )
    pi_df = pi_df.assign(
        pi_is_power_user=pi_df["pi_is_power_user"].str.strip() == "Yes",
    )
    return pi_df


def load_storage_update_df(storage_update_form_path: os.PathLike) -> pd.DataFrame:
    """Load dataframe containing updates to PI dataframe.

    Parameters
    ----------
    storage_update_form_path : str
        Path to the storage update form.

    Returns
    -------
    DataFrame
        Dataframe containing updates to PI storage needs.
    """
    storage_update_df = pd.read_excel(storage_update_form_path, engine="openpyxl")
    storage_update_df = storage_update_df.rename(
        columns={
            "Completion time": "timestamp",
            "Email": "email",
            "First name": "first_name",
            "Last name": "last_name",
            ("Additional storage needs (in TB)"): "new_storage",
            "New speed code": "speed_code",
            ("New secure project spaces names"): "access_groups",
            ("Consent"): "agree",
            "Please feel free to leave any feedback": "feedback",
            "Account closure2": "account_closed",
        },
    )
    storage_update_df = storage_update_df.assign(
        agree=storage_update_df["agree"].str.strip() == "Yes",
        account_closed=storage_update_df["account_closed"].str.strip() == "Yes",
    )
    return storage_update_df


def add_pis_to_user_df(pi_df: pd.DataFrame, user_df: pd.DataFrame) -> pd.DataFrame:
    """Add PI user accounts to the user dataframe.

    PI user account information is stored in the PI Google Forms data by
    default, but is easier to work with if it's grouped with the other user
    account data.

    Parameters
    ----------
    pi_df : DataFrame
        Data frame including PI storage and PI account power user information.
    user_df : DataFrame
        Data frame including user account information.

    Returns
    -------
    DataFrame
        User dataframe with rows describing PI user accounts appended to the
        end.
    """
    pi_user_df = pi_df.loc[
        :,
        [
            "start_timestamp",
            "email",
            "first_name",
            "last_name",
            "pi_is_power_user",
        ],
    ]
    pi_user_df = pi_user_df.assign(
        pi_last_name=pi_user_df["last_name"],
        end_timestamp=(None),
    )
    pi_user_df = pi_user_df.rename(columns={"pi_is_power_user": "power_user"})
    return pd.concat([user_df, pi_user_df], ignore_index=True)


def preprocess_forms(
    pi_path: os.PathLike,
    user_path: os.PathLike,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load Google Forms data and rearrange it.

    Specifically, this loads both relevant sheets and adds PI accounts to the
    users table.

    Parameters
    ----------
    pi_path : str
        Path to the PI form data
    user_path : str
        Path to the user form data

    Returns
    -------
    tuple of DataFrame
        A tuple containing the resulting PI data frame then the user data
        frame.
    """
    pi_df = load_pi_df(pi_path)
    user_df = load_user_df(user_path)
    user_df = add_pis_to_user_df(pi_df, user_df)

    return (pi_df, user_df)


def summarize_all_pi_bills(
    paths: list[os.PathLike],
    quarter_start_iso: str,
    out_file: os.PathLike,
) -> None:
    """Print a summary of all PI bills."""
    pi_df, user_df = preprocess_forms(paths[0], paths[2])
    storage_update_df = load_storage_update_df(paths[1])
    user_update_df = load_user_update_df(paths[3])

    quarter_start = datetime.date.fromisoformat(quarter_start_iso)

    storage_record = StorageRecord(pi_df, storage_update_df)
    power_users_record = PowerUsersRecord(user_df, user_update_df)

    policy = BillingPolicy()

    summary = [
        {
            "pi": pi_last_name,
            "storage_amount": policy.get_quarterly_storage_amount(
                storage_record,
                pi_last_name,
                quarter_start,
            ),
            "storage_price": policy.get_quarterly_storage_price(
                storage_record,
                pi_last_name,
                quarter_start,
            ),
            "billed_power_users": len(
                [
                    user
                    for user in policy.enumerate_quarterly_power_user_prices(
                        power_users_record,
                        pi_last_name,
                        quarter_start,
                    )
                    if user[3] > 0
                ],
            ),
            "compute_price": policy.get_quarterly_power_user_price(
                power_users_record,
                pi_last_name,
                quarter_start,
            ),
            "speed_code": storage_record.get_speed_code(
                pi_last_name,
                datetime.date.today(),
            ),
        }
        for pi_last_name in pi_df.loc[:, "last_name"]
        if policy.is_billable_pi(storage_record, pi_last_name, quarter_start)
    ]
    pd.DataFrame(
        {
            "pi": [pi["pi"] for pi in summary],
            "storage_amount": [pi["storage_amount"] for pi in summary],
            "storage_price": [pi["storage_price"] for pi in summary],
            "billed_power_users": [pi["billed_power_users"] for pi in summary],
            "compute_price": [pi["compute_price"] for pi in summary],
            "total_price": [
                pi["storage_price"] + pi["compute_price"] for pi in summary
            ],
            "speed_code": [pi["speed_code"] for pi in summary],
        },
    ).to_excel(out_file, index=False, engine="openpyxl")

    total_storage = sum(pi_bill["storage_price"] for pi_bill in summary)
    total_compute = sum(pi_bill["compute_price"] for pi_bill in summary)
    total = total_storage + total_compute

    print(f"Total (Storage): {total_storage}")
    print(f"Mean (Storage): {total_storage / len(summary)}")
    print(f"Total (Compute): {total_compute}")
    print(f"Mean (Compute): {total_compute / len(summary)}")
    print(f"Total (Overall): {total}")
    print(f"Mean (Overall): {total / len(summary)}")


def generate_all_pi_bills(
    paths: list[os.PathLike],
    quarter_start_iso: str,
    out_dir: os.PathLike,
) -> None:
    """Loop through all PIs and save a bill for each.

    Parameters
    ----------
    paths
        Path to the PI form data, storage update form data, user form data,
        and user update form data, in that order.
    quarter_start_iso
        ISO formatted end date of the billing quarter.
    out_dir
        Directory into which to output bill text files.
    """
    [pi_path, storage_update_path, user_path, user_update_path] = paths
    pi_df, _ = preprocess_forms(pi_path, user_path)

    for pi_last_name in pi_df.loc[:, "last_name"]:
        out_file = (
            Path(out_dir) / f"pi-{pi_last_name}_quarter-{quarter_start_iso}_bill.tex"
        )
        generate_pi_bill(
            [pi_path, storage_update_path, user_path, user_update_path],
            pi_last_name,
            quarter_start_iso,
            out_file,
        )


def generate_pi_bill(
    paths: list[os.PathLike],
    pi_last_name: str,
    quarter: str,
    out_file: os.PathLike | None = None,
) -> None:
    """Open data files and produce a report for one PI.

    If the PI is not billable this quarter, this will do nothing.

    Parameters
    ----------
    paths
        Paths to PI form data, storage update form data, user form data,
        and user update form data, in that order.
    pi_last_name
        Last name of the PI to bill.
    quarter
        ISO formatted start date of the billing quarter.
    out_file
        Path to output text file.
    """
    pi_df, user_df = preprocess_forms(paths[0], paths[2])
    storage_update_df = load_storage_update_df(paths[1])
    user_update_df = load_user_update_df(paths[3])

    quarter_start = datetime.date.fromisoformat(quarter)

    storage_record = StorageRecord(pi_df, storage_update_df)
    power_users_record = PowerUsersRecord(user_df, user_update_df)

    policy = BillingPolicy()

    if not policy.is_billable_pi(storage_record, pi_last_name, quarter_start):
        return

    bill_tex = policy.generate_quarterly_bill_tex(
        storage_record,
        power_users_record,
        pi_last_name,
        quarter_start,
        env,
    )
    if out_file is not None:
        with Path(out_file).open("w", encoding="utf-8") as writable:
            writable.write(bill_tex)


def gen_parser() -> argparse.ArgumentParser:
    """Generate a command-line parser."""
    parser = argparse.ArgumentParser(description="Process CBS Server billing data.")
    parser.add_argument("pi_form", type=str, help="path to the PI form data")
    parser.add_argument(
        "storage_update_form",
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
        "quarter_start",
        type=str,
        help="first day of the quarter to bill",
    )
    parser.add_argument(
        "out_dir",
        type=str,
        help="directory into which to output bill files",
    )

    return parser


if __name__ == "__main__":
    args = gen_parser().parse_args()
    generate_all_pi_bills(
        [
            args.pi_form,
            args.storage_update_form,
            args.user_form,
            args.user_update_form,
        ],
        args.quarter_start,
        args.out_dir,
    )
    summarize_all_pi_bills(
        [
            args.pi_form,
            args.storage_update_form,
            args.user_form,
            args.user_update_form,
        ],
        args.quarter_start,
        Path(args.out_dir) / f"summary_{args.quarter_start}.xlsx",
    )
