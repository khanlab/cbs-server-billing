"""Handling of user forms."""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import NamedTuple

import pandas as pd
from attrs import Attribute, define, evolve, field
from typing_extensions import Self

from cbsserverbilling.records import User


@define(frozen=True)
class Update:
    """An update to a user."""

    date: datetime.date
    power_user: bool | None = None
    pi_name: str | None = None


def _both_defined(
    instance: UpdateUser,
    _: Attribute[frozenset[Update]],
    value: frozenset[Update],
) -> None:
    if not [update for update in value if update.power_user is not None]:
        raise InvalidUserError(instance, "power_user")
    if not [update for update in value if update.pi_name]:
        raise InvalidUserError(instance, "pi_name")


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


def enumerate_all_users(
    power_user_df: pd.DataFrame,
    power_user_update_df: pd.DataFrame,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[UpdateUser]:
    """Generate a list of all users with an active account.

    Parameters
    ----------
    power_user_df
        Table of new user requests
    power_user_update_df
        Table of user update requests
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
    user_df = power_user_df.loc[
        power_user_df["start_timestamp"].dt.date < end_date,
        [
            "last_name",
            "start_timestamp",
            "end_timestamp",
            "email",
            "pi_last_name",
            "power_user",
        ],
    ]
    update_df = power_user_update_df.loc[
        (power_user_update_df["timestamp"].dt.date < end_date)
        & (pd.notna(power_user_update_df["new_end_timestamp"])),
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
        user for user in users if (not user.end_date) or (user.end_date > start_date)
    ]


class InvalidUserError(Exception):
    """Exception raised when a user is misspecified."""

    def __init__(self, user: User, missing_attrs: str) -> None:
        """Information about the misspecified user."""
        super().__init__(f"User {user} is missing required info {missing_attrs}")


class InactiveUserError(Exception):
    """Exception raised when a user operated on while inactive."""

    def __init__(self, user: User, date: datetime.date) -> None:
        """Information about the inactive user."""
        super().__init__(f"User {user} is inactive on date {date}")


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
