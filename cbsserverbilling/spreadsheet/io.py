"""Functions for reading spreadsheet data."""

from __future__ import annotations

import os

import pandas as pd


def load_user_df(user_form_path: os.PathLike[str] | str) -> pd.DataFrame:
    """Load user Google Forms data into a usable pandas dataframe.

    Parameters
    ----------
    user_form_path
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
            "UWO.CA email address": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "PI last name": "pi_last_name",
            "Contract end date": "end_timestamp",
            "Do you need your account to be a Power User account": "power_user",
        },
    )
    user_df = user_df.map(lambda x: x.strip().lower() if isinstance(x, str) else x)
    user_df = user_df.assign(
        power_user=user_df["power_user"] == "yes",
    )
    return user_df


def load_user_update_df(user_update_form_path: os.PathLike[str] | str) -> pd.DataFrame:
    """Load dataframe containing updates to user dataframe.

    Parameters
    ----------
    user_update_form_path
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
            "UWO.CA email address": "email",
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
    user_update_df = user_update_df.map(lambda x: x.strip().lower() if isinstance(x, str) else x)
    user_update_df = user_update_df.assign(
        agree=user_update_df["agree"] == "yes",
        new_power_user=user_update_df["new_power_user"].map(
            lambda x: None if pd.isna(x) else x == "power user",
        ),
    )
    return user_update_df


def load_pi_df(pi_form_path: os.PathLike[str] | str) -> pd.DataFrame:
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
            "UWO email address": "email",
            "First Name": "first_name",
            "Last Name": "last_name",
            (
                "Would you like your account to be a power user account?"
            ): "pi_is_power_user",
            "Speed code": "speed_code",
            "Required storage needs (in TB)": "storage",
        },
    )
    pi_df = pi_df.map(lambda x: x.strip().lower() if isinstance(x, str) else x)
    pi_df = pi_df.assign(
        pi_is_power_user=pi_df["pi_is_power_user"] == "yes",
    )
    return pi_df


def load_storage_update_df(
    storage_update_form_path: os.PathLike[str] | str,
) -> pd.DataFrame:
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
            "UWO.CA email address": "email",
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
    storage_update_df = storage_update_df.map(lambda x: x.strip().lower() if isinstance(x, str) else x)
    storage_update_df = storage_update_df.assign(
        agree=storage_update_df["agree"] == "yes",
        account_closed=storage_update_df["account_closed"] == "yes",
    )
    return storage_update_df
