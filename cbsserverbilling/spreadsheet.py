"""Module containing spreadsheet-based billing records."""

from __future__ import annotations

import datetime
import logging
import os
from typing import Literal, NamedTuple

import pandas as pd
from attrs import define

from cbsserverbilling.records import BillableProjectRecord, User

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class AccountRequestTuple(NamedTuple):
    start_timestamp: pd.Timestamp
    last_name: str
    email: str
    pi_last_name: str
    power_user: bool
    end_timestamp: pd.Timestamp


@define
class AccountRequest:
    timestamp: datetime.datetime
    name: str
    email: str
    pi_name: str
    power_user: bool
    end_date: datetime.date | None = None

    @classmethod
    def from_pd_tuple(cls, tuple_: AccountRequestTuple):
        return cls(
            timestamp=tuple_.start_timestamp.to_pydatetime(),
            name=tuple_.last_name,
            email=tuple_.email,
            pi_name=tuple_.pi_last_name,
            power_user=tuple_.power_user,
            end_date=tuple_.end_timestamp.to_pydatetime().date()
            if pd.notna(tuple_.end_timestamp)
            else None,
        )


@define
class AccountUpdate:
    timestamp: datetime.datetime
    name: str
    email: str
    pi_name: str | None = None
    power_user: bool | None = None
    end_date: datetime.date | None = None


@define
class SpreadsheetBillableProjectRecord(BillableProjectRecord):
    """Billable project record derived from a set of spreadsheets."""

    storage_record: SpreadsheetStorageRecord
    power_users_record: SpreadsheetPowerUsersRecord
    pi_last_name: str
    speed_code: str
    open_date: datetime.date
    close_date: datetime.date | None = None

    def get_pi_full_name(self) -> str:
        """Get a PI's full name.

        Returns
        -------
        str
            Full name of the PI
        """
        return self.storage_record.get_pi_full_name(self.pi_last_name)

    def get_storage_start(self) -> datetime.date:
        """Get a PI's storage start date."""
        return self.open_date

    def get_close_date(self) -> datetime.date | None:
        """Get a PI's account closure date, if any."""
        return self.close_date

    def get_storage_amount(self, date: datetime.date) -> float:
        """Get the amount of storage allocated to this PI on a given date.

        Parameters
        ----------
        date
            Date to check storage price.

        Returns
        -------
        float
            Amount of storage (in TB) allocated to this PI.
        """
        return self.storage_record.get_storage_amount(
            self.pi_last_name,
            self.speed_code,
            date,
        )

    def get_speed_code(self, date: datetime.date) -> str:  # noqa: ARG002
        """Get the speed code associated with this project on a date.

        Parameters
        ----------
        date
            Date on which to check the speed code.
        """
        return self.speed_code

    def enumerate_all_users(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> list[User]:
        """Generate a list of all users with an active account.

        Parameters
        ----------
        start_date
            First date to consider.
        end_date
            Last date to consider.
        """


@define
class SpreadsheetStorageRecord:
    """Record describing all PIs' storage use."""

    storage_df: pd.DataFrame
    storage_update_df: pd.DataFrame

    def get_pi_full_name(self, pi_last_name: str) -> str:
        """Get a PI's full name.

        Parameters
        ----------
        pi_last_name
            Last name of the PI

        Returns
        -------
            Full name of the PI
        """
        return (
            self.storage_df.loc[
                self.storage_df["last_name"] == pi_last_name,
                "first_name",
            ].iloc[0]
            + " "
            + pi_last_name
        )

    def get_storage_start(self, pi_last_name: str) -> datetime.date:
        """Get a PI's storage start date.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.

        Returns
        -------
        date
            Date this PI's storage started.
        """
        return (
            self.storage_df.loc[
                self.storage_df["last_name"] == pi_last_name,
                "start_timestamp",
            ]
            .iloc[0]
            .date()
        )

    def get_pi_account_close_date(self, pi_last_name: str) -> datetime.date | None:
        """Get a PI's account closure date, if any.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.

        Returns
        -------
        date or None
            Date this PI's account was closed, if any.
        """
        closure_row = self.storage_update_df.loc[
            (self.storage_update_df["last_name"] == pi_last_name)
            & (self.storage_update_df["account_closed"]),
            "timestamp",
        ]
        if closure_row.empty:
            return None
        return closure_row.iloc[0].date()

    def get_storage_amount(
        self,
        pi_last_name: str,
        speed_code: str,
        date: datetime.date,
    ) -> float:
        """Get the amount of storage allocated to this PI on a given date.

        Parameters
        ----------
        pi_last_name
            Last name of the PI.
        speed_code
            Speed code associated with the billable project
        date
            Date to check storage price.

        Returns
        -------
        float
            Amount of storage (in TB) allocated to this PI.
        """
        total_storage = 0
        pi_storage = self.storage_df.loc[
            (self.storage_df["last_name"] == pi_last_name)
            & (self.storage_df["speed_code"] == speed_code)
            & (self.storage_df["start_timestamp"].dt.date <= date),
            :,
        ]
        if len(pi_storage) > 0:
            total_storage += pi_storage.loc[:, "storage"].iloc[0]

        pi_storage_updates = self.storage_update_df.loc[
            (self.storage_update_df["last_name"] == pi_last_name)
            & (self.storage_update_df["timestamp"].dt.date <= date),
            :,
        ]
        if len(pi_storage_updates) > 0:
            total_storage += pi_storage_updates.loc[:, "new_storage"].sum()
        return total_storage

    def get_speed_code(self, pi_last_name: str, date: datetime.date) -> str:
        """Get the speed code associated with this PI on a date.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.
        date: date
            Date on which to check the speed code.

        Returns
        -------
        str
            Speed code associated with this PI.
        """
        speed_code_updates = self.storage_update_df.loc[
            (self.storage_update_df["last_name"] == pi_last_name)
            & (pd.notna(self.storage_update_df["speed_code"]))
            & (self.storage_update_df["timestamp"].dt.date <= date),
            :,
        ]
        return str(
            self.storage_df.loc[
                self.storage_df["last_name"] == pi_last_name,
                "speed_code",
            ].iloc[0]
            if speed_code_updates.empty
            else speed_code_updates.loc[
                speed_code_updates["timestamp"].idxmax(),
                "speed_code",
            ],
        )


@define
class SpreadsheetPowerUsersRecord:
    """Record describing the users described by the forms.

    Attributes
    ----------
    power_user_df : DataFrame
        Dataframe containing each user during the quarter. Should be generated
        by this module to apply the expected structure.
    power_user_update_df : DataFrame
        Dataframe containing updates to user accounts defined in the power
        user dataframe.
    """

    power_user_df: pd.DataFrame
    power_user_update_df: pd.DataFrame

    def enumerate_all_users(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> list[User]:
        """Generate a list of all users with an active account.

        Parameters
        ----------
        start_date
            First date to consider.
        end_date
            Last date to consider.

        Returns
        -------
        list of tuple
            A tuple for each user who was active on any day in the given
            range. The tuple contains the user's name, start date, and end
            date.
        """
        user_df = self.power_user_df.loc[
            self.power_user_df["start_timestamp"].dt.date < end_date,
            ["last_name", "start_timestamp", "end_timestamp"],
        ]
        update_df = self.power_user_update_df.loc[
            (self.power_user_update_df["timestamp"].dt.date < end_date)
            & (pd.notna(self.power_user_update_df["new_end_timestamp"])),
            ["last_name", "timestamp", "new_end_timestamp"],
        ].assign(applied=False)
        users = []
        for term in user_df.itertuples():
            updates = update_df.loc[
                (update_df["last_name"] == term.last_name)
                & (update_df["timestamp"] > term.start_timestamp),
                :,
            ]
            term_end_date: datetime.date | None = (
                term.end_timestamp.date() if pd.notna(term.end_timestamp) else None
            )
            for update in updates.itertuples():
                if update.applied:
                    logger.warning(
                        "Update %s already applied to a different term.",
                        update,
                    )
                if (not term_end_date) or (update.timestamp.date() < term_end_date):
                    term_end_date = update.new_end_timestamp.date()
                    update_df.loc[update.Index, "applied"] = True
            if (not term_end_date) or (term_end_date > start_date):
                users.append(
                    User(
                        name=term.last_name,
                        power_user=False,
                        start_date=term.start_timestamp.date(),
                        end_date=term_end_date,
                    ),
                )
        update_terms = []
        for unused_update in update_df.loc[~update_df["applied"], :].itertuples():
            # These should be new terms for expired users.
            if unused_update.last_name not in {user.name for user in users}:
                raise InvalidUpdateError(str(unused_update))
            used_update = False
            for term in [
                term for term in update_terms if term.name == unused_update.last_name
            ]:
                if (term.end_date) and (unused_update.timestamp.date() > term.end_date):
                    continue
                term.end_date = unused_update.new_end_timestamp.date()
                used_update = True
                break
            if not used_update:
                update_terms.append(
                    User(
                        name=unused_update.last_name,
                        power_user=False,
                        start_date=unused_update.timestamp.date(),
                        end_date=unused_update.new_end_timestamp.date(),
                    ),
                )

        return users + update_terms

    def enumerate_power_users(
        self,
        pi_last_name: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> list[tuple[str, datetime.date, datetime.date]]:
        """Generate a list of power users associated with this PI.

        Parameters
        ----------
        pi_last_name : str
            PI of the users to enumerate.
        start_date : date
            First date to consider.
        end_date : date
            Last date to consider.

        Returns
        -------
        list of namedtuple
            A namedtuple for each user who was active on any day in the given
            range, where each namedtuple contains the user's last name, start
            date, and end date, in that order.
        """
        out_df = self.power_user_df.loc[
            self.power_user_df["pi_last_name"] == pi_last_name,
            ["last_name", "start_timestamp"],
        ]
        out_list = []
        for name in out_df.loc[
            out_df["start_timestamp"].dt.date <= end_date,
            "last_name",
        ]:
            for term in self.describe_user(name, start_date, end_date):
                if not term[0]:
                    continue
                out_list.append((name, term[1], term[2]))

        return sorted(out_list, key=lambda x: x[1])

    def describe_user(
        self,
        last_name: str,
        period_start: datetime.date,
        period_end: datetime.date,
    ) -> list[
        tuple[Literal[True], datetime.date, datetime.date]
        | tuple[Literal[False], None, None]
    ]:
        """Check whether a user was a power user in a given period.

        Parameters
        ----------
        last_name : str
            The user's last name.
        period_start : date
            First day of the period to check.
        period_end : date
            Last day of the period to check.

        Returns
        -------
        list of (bool, date or None, date or None)
            Tuples describing whether the user was a power user during each
            of their terms during the period, then if so, the start and end
            dates of those terms.
        """
        orig_row = self.power_user_df.loc[
            (self.power_user_df["last_name"] == last_name)
            & (self.power_user_df["start_timestamp"].dt.date <= period_end),
            :,
        ].copy()
        if len(orig_row) == 0:
            return [(False, None, None)]

        # Only want the most recent term
        most_recent = orig_row.loc[orig_row["start_timestamp"].idxmax()]
        relevant_updates = self.power_user_update_df.loc[
            (self.power_user_update_df["last_name"] == last_name)
            & (self.power_user_update_df["timestamp"].dt.date <= period_end)
            & (
                (self.power_user_update_df["new_end_timestamp"].notna())
                | (self.power_user_update_df["new_power_user"].notna())
            ),
            ["timestamp", "new_end_timestamp", "new_power_user"],
        ]
        # Only want updates after this term started
        relevant_updates = relevant_updates.loc[
            (
                relevant_updates["timestamp"].dt.date
                >= most_recent["start_timestamp"].date()
            ),
            :,
        ]
        for update in relevant_updates.sort_values(by=["timestamp"]).itertuples():
            if update.timestamp.date() > most_recent["end_timestamp"].date():
                most_recent = gen_new_term_from_row(most_recent, update)
            else:
                most_recent = update_term_from_row(most_recent, update)

        if not (
            pd.isna(most_recent["end_timestamp"])
            or most_recent["end_timestamp"].date() >= period_start
        ):
            return [(False, None, None)]

        return [
            (
                True,
                most_recent["start_timestamp"].date(),
                most_recent["end_timestamp"].date(),
            )
            if most_recent["power_user"]
            else (False, None, None),
        ]


def gen_new_term_from_row(orig_row: pd.Series, update: pd.Series) -> pd.Series:
    """Update a user's entry to consider a new term."""
    orig_row["start_timestamp"] = update.timestamp
    if pd.notna(update.new_end_timestamp):
        orig_row["end_timestamp"] = update.new_end_timestamp
    else:
        print("User reinstated with no new end date")
    if pd.notna(update.new_power_user):
        if update.new_power_user:
            orig_row["power_user"] = True
        else:
            orig_row["power_user"] = False
    return orig_row


def update_term_from_row(orig_row: pd.Series, update: pd.Series):
    """Update a user's existing term."""
    if pd.notna(update.new_end_timestamp):
        orig_row["end_timestamp"] = update.new_end_timestamp
    if pd.notna(update.new_power_user):
        if update.new_power_user:
            if not orig_row["power_user"]:
                # They became a power user with the update
                orig_row["power_user"] = True
                orig_row["start_timestamp"] = update.timestamp
        elif orig_row["power_user"]:
            # They stopped being a power user at the update
            # timestamp, so update appropriately.
            orig_row["end_timestamp"] = update.timestamp
    return orig_row


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
            "Email": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "PI last name": "pi_last_name",
            "Contract end date": "end_timestamp",
            "Do you need your account to be a Power User account": "power_user",
        },
    )
    user_df = user_df.assign(power_user=user_df["power_user"].str.strip() == "Yes")
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
    pi_df
        Data frame including PI storage and PI account power user information.
    user_df
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


class InvalidUpdateError(Exception):
    """Exception raised when a user update doesn't apply to an existent user."""

    def __init__(self, update_str: str) -> None:
        """update_str: __str__ of the failed update."""
        super().__init__(f"Update {update_str} does not apply to an existent user.")
