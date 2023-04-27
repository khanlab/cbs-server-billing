"""Module containing spreadsheet-based billing records."""

from __future__ import annotations

import datetime
import logging
import os
from collections.abc import Iterable
from typing import NamedTuple

import pandas as pd
from attrs import Attribute, define, evolve, field
from typing_extensions import Self

from cbsserverbilling.records import BillableProjectRecord, User

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@define(frozen=True)
class Update:
    """An update to a user."""

    date: datetime.date
    power_user: bool | None = None
    pi_name: str | None = None


class InvalidUserError(Exception):
    """Exception raised when a user is misspecified."""

    def __init__(self, user: User, missing_attrs: str) -> None:
        """Information about the misspecified user."""
        super().__init__(f"User {user} is missing required info {missing_attrs}")


def _both_defined(
    instance: UpdateUser,
    _: Attribute[frozenset[Update]],
    value: frozenset[Update],
) -> None:
    if not [update for update in value if update.power_user is not None]:
        raise InvalidUserError(instance, "power_user")
    if not [update for update in value if update.pi_name]:
        raise InvalidUserError(instance, "pi_name")


class InactiveUserError(Exception):
    """Exception raised when a user operated on while inactive."""

    def __init__(self, user: User, date: datetime.date) -> None:
        """Information about the inactive user."""
        super().__init__(f"User {user} is inactive on date {date}")


@define(frozen=True)
class UpdateUser(User):
    """A user with updates to handle its changes."""

    updates: frozenset[Update] = field(default=frozenset(), validator=[_both_defined])

    def check_valid_date(self, date: datetime.date) -> None:
        """Check that the user was active on this date."""
        if not self.is_active(date):
            raise InactiveUserError(self, date)

    def is_power_user(self, date: datetime.date) -> bool:
        """Check whether a user was a power user on this date."""
        self.check_valid_date(date)
        return max(  # type: ignore[reportGeneralTypeIssues]
            (
                update
                for update in self.updates
                if (update.power_user is not None) and (update.date <= date)
            ),
            key=lambda update: update.date,
        ).power_user

    def get_pi_name(self, date: datetime.date) -> str:
        """Check a user's PI on this date."""
        self.check_valid_date(date)
        return max(  # type: ignore[reportGeneralTypeIssues]
            (
                update
                for update in self.updates
                if (update.pi_name is not None) and (update.date <= date)
            ),
            key=lambda update: update.date,
        ).pi_name


class AccountRequestTuple(NamedTuple):
    """Tuple describing an account request from pandas."""

    start_timestamp: pd.Timestamp
    last_name: pd.StringDtype
    email: pd.StringDtype
    pi_last_name: pd.StringDtype
    power_user: pd.BooleanDtype
    end_timestamp: pd.Timestamp


@define
class AccountRequest:
    """Dataclass describing a new account request."""

    timestamp: datetime.datetime
    name: str
    email: str
    pi_name: str
    power_user: bool
    end_date: datetime.date | None = None

    @classmethod
    def from_pd_tuple(cls, tuple_: AccountRequestTuple) -> Self:
        """Generate a request from a pandas tuple."""
        return cls(
            timestamp=tuple_.start_timestamp.to_pydatetime(),
            name=str(tuple_.last_name),
            email=str(tuple_.email),
            pi_name=str(tuple_.pi_last_name),
            power_user=bool(tuple_.power_user),
            end_date=tuple_.end_timestamp.to_pydatetime().date()
            if pd.notna(tuple_.end_timestamp)
            else None,
        )

    def create_user(self) -> UpdateUser:
        """Generate a new user from this request."""
        return UpdateUser(
            name=self.name,
            email=self.email,
            start_date=self.timestamp.date(),
            end_date=self.end_date,
            updates=frozenset(
                [
                    Update(
                        date=self.timestamp.date(),
                        power_user=self.power_user,
                        pi_name=self.pi_name,
                    ),
                ],
            ),
        )

    def update_user(self, user: UpdateUser) -> UpdateUser:
        """Update an existing user from this request."""
        update = Update(
            pi_name=self.pi_name,
            power_user=self.power_user,
            date=self.timestamp.date(),
        )
        return evolve(
            user,
            end_date=self.end_date,
            updates=user.updates | frozenset([update]),
        )

    def handle(self, existing_users: Iterable[UpdateUser]) -> list[UpdateUser]:
        """Handle this request given some existing users."""
        if self.email in {user.email for user in existing_users}:
            to_update = max(
                (user for user in existing_users if user.email == self.email),
                key=lambda user: user.start_date,
            )
            return list(
                set(existing_users) - {to_update} | {self.update_user(to_update)},
            )
        return [*existing_users, self.create_user()]


class AccountUpdateTuple(NamedTuple):
    """Tuple describing an account request from pandas."""

    timestamp: pd.Timestamp
    last_name: pd.StringDtype
    email: pd.StringDtype
    pi_last_name: str
    new_power_user: bool
    new_end_timestamp: pd.Timestamp


class InapplicableUpdateError(Exception):
    """Exception raised when an error can't be applied."""

    def __init__(self, update: AccountUpdate) -> None:
        """Describe the update problem."""
        super().__init__(f"There is no user to which to apply update {update}")


class UserAlreadyActiveError(Exception):
    """Exception raised when an active user is reinstated."""

    def __init__(self, user: UpdateUser, update: AccountUpdate) -> None:
        """Describe the update problem."""
        super().__init__(f"User {user} can't be reinstated by update {update}")


@define
class AccountUpdate:
    """Dataclass describing an account update."""

    timestamp: datetime.datetime
    name: str
    email: str
    pi_name: str | None = None
    power_user: bool | None = None
    end_date: datetime.date | None = None

    @classmethod
    def from_pd_tuple(cls, tuple_: AccountUpdateTuple) -> Self:
        """Generate from a pandas tuple."""
        return cls(
            timestamp=tuple_.timestamp.to_pydatetime(),
            name=str(tuple_.last_name),
            email=str(tuple_.email),
            pi_name=str(tuple_.pi_last_name) if pd.notna(tuple_.pi_last_name) else None,
            power_user=bool(tuple_.new_power_user)
            if pd.notna(tuple_.new_power_user)
            else None,
            end_date=tuple_.new_end_timestamp.to_pydatetime().date()
            if pd.notna(tuple_.new_end_timestamp)
            else None,
        )

    def update_user(self, user: UpdateUser) -> UpdateUser:
        """Update an existing user from this request."""
        update = Update(
            date=self.timestamp.date(),
            power_user=self.power_user,
            pi_name=self.pi_name,
        )
        return evolve(user, updates=user.updates | frozenset([update]))

    def reinstate_user(self, user: UpdateUser) -> UpdateUser:
        """Reinstate an existing user whose term has expired."""
        if user.is_active(self.timestamp.date()):
            raise UserAlreadyActiveError(user, self)

        updates = {"end_date": self.end_date} if self.end_date is not None else {}
        pi_name = self.pi_name or user.get_pi_name(
            user.end_date,  # type: ignore[reportGeneralTypeIssues]
        )
        power_user = (
            self.power_user
            if self.power_user is not None
            else user.is_power_user(
                user.end_date,  # type: ignore[reportGeneralTypeIssues]
            )
        )
        return evolve(
            user,
            start_date=self.timestamp.date(),
            **updates,
            updates=frozenset(
                [
                    Update(
                        date=self.timestamp.date(),
                        pi_name=pi_name,
                        power_user=power_user,
                    ),
                ],
            ),
        )

    def handle(self, existing_users: Iterable[UpdateUser]) -> list[UpdateUser]:
        """Handle this request given some existing users."""
        if self.email not in {user.email for user in existing_users}:
            raise InapplicableUpdateError(self)
        to_update = max(
            (user for user in existing_users if user.email == self.email),
            key=lambda user: user.start_date,
        )
        if to_update.is_active(self.timestamp.date()):
            return list(
                set(existing_users) - {to_update} | {self.update_user(to_update)},
            )
        return [*existing_users, self.reinstate_user(to_update)]


@define
class SpreadsheetBillableProjectRecord(BillableProjectRecord):
    """Billable project record derived from a set of spreadsheets."""

    storage_record: SpreadsheetStorageRecord
    power_users_record: SpreadsheetPowerUsersRecord
    pi_last_name: str
    speed_code: str
    open_date: datetime.date
    close_date: datetime.date | None = None
    has_power_users: bool = False

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
    ) -> Iterable[User]:
        """Generate a list of all users with an active account.

        Parameters
        ----------
        start_date
            First date to consider.
        end_date
            Last date to consider.
        """
        days = [
            start_date + datetime.timedelta(days=delta)
            for delta in range((end_date - start_date).days + 1)
        ]
        return [
            user
            for user in self.power_users_record.enumerate_all_users(
                start_date,
                end_date,
            )
            if any((user.get_pi_name(date) == self.pi_last_name) for date in days)
        ]

    def enumerate_power_users(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> Iterable[User]:
        """Generate a list of power users associated with this PI.

        Parameters
        ----------
        start_date
            First date to consider.
        end_date
            Last date to consider.
        """
        return (
            self.power_users_record.enumerate_power_users(
                self.pi_last_name,
                start_date,
                end_date,
            )
            if self.has_power_users
            else []
        )


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
    ) -> list[UpdateUser]:
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
            [
                "last_name",
                "start_timestamp",
                "end_timestamp",
                "email",
                "pi_last_name",
                "power_user",
            ],
        ]
        update_df = self.power_user_update_df.loc[
            (self.power_user_update_df["timestamp"].dt.date < end_date)
            & (pd.notna(self.power_user_update_df["new_end_timestamp"])),
            [
                "last_name",
                "timestamp",
                "new_end_timestamp",
                "email",
                "pi_last_name",
                "new_power_user",
            ],
        ].assign(applied=False)

        users = []
        requests = [
            AccountRequest.from_pd_tuple(tuple_)
            for tuple_ in user_df.itertuples(name="AccountRequestTuple")
        ]
        updates = [
            AccountUpdate.from_pd_tuple(tuple_)
            for tuple_ in update_df.itertuples(name="AccountUpdateTuple")
        ]
        changes = sorted(requests + updates, key=lambda change: change.timestamp)
        for change in changes:
            users = change.handle(users)

        return [
            user
            for user in users
            if (not user.end_date) or (user.end_date > start_date)
        ]

    def enumerate_power_users(
        self,
        pi_last_name: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> list[UpdateUser]:
        """Generate a list of power users associated with this PI.

        Parameters
        ----------
        pi_last_name
            PI of the users to enumerate.
        start_date
            First date to consider.
        end_date
            Last date to consider.
        """
        users = self.enumerate_all_users(start_date, end_date)
        days = [
            start_date + datetime.timedelta(days=delta)
            for delta in range((end_date - start_date).days + 1)
        ]
        return [
            user
            for user in users
            if any(
                ((user.get_pi_name(date) == pi_last_name) and user.is_power_user(date))
                for date in days
            )
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
