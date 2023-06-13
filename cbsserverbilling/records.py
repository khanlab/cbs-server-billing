"""Interface for getting raw CBS Server usage information."""

from __future__ import annotations

import datetime
from abc import ABCMeta, abstractmethod
from collections.abc import Iterable

from attrs import Attribute, define, field


def _check_dates(
    instance: User,
    _: Attribute[datetime.date | None],
    value: datetime.date | None,
) -> None:
    if value and (value < instance.start_date):
        raise UserDateRangeError(instance, instance.start_date, value)


@define(frozen=True)
class User(metaclass=ABCMeta):
    """A user of the CBS Server."""

    # pylint: disable=too-few-public-methods
    name: str
    email: str
    start_date: datetime.date
    end_date: datetime.date | None = field(default=None, validator=[_check_dates])

    def is_active(self, date: datetime.date) -> bool:
        """Check if the user is active on a given date."""
        return (self.start_date <= date) and (
            (not self.end_date) or (self.end_date >= date)
        )

    @abstractmethod
    def is_power_user(self, date: datetime.date) -> bool:
        """Check whether a user was a power user on this date."""

    @abstractmethod
    def get_pi_name(self, date: datetime.date) -> str:
        """Check a user's PI on this date."""


class BillableProjectRecord(metaclass=ABCMeta):
    """Record of one billable project."""

    @abstractmethod
    def get_pi_last_name(self) -> str:
        """Get the project PI's last name."""

    @abstractmethod
    def get_pi_full_name(self) -> str:
        """Get the project PI's full name."""

    @abstractmethod
    def get_storage_start(self) -> datetime.date:
        """Get the project's storage start date."""

    @abstractmethod
    def get_close_date(self) -> datetime.date | None:
        """Get the project's account closure date, if any."""

    @abstractmethod
    def get_storage_amount(self, date: datetime.date) -> float:
        """Get the amount of storage allocated to this project on a given date.

        Parameters
        ----------
        date
            Date to check storage price.

        Returns
        -------
            Amount of storage (in TB) allocated to this PI.
        """

    @abstractmethod
    def get_speed_code(self, date: datetime.date) -> str:
        """Get the speed code associated with this project on a date.

        Parameters
        ----------
        date
            Date on which to check the speed code.
        """

    @abstractmethod
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

    @abstractmethod
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


class UserDateRangeError(ValueError):
    """Exception raised when a user's date range is invalid."""

    def __init__(
        self,
        user: User,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> None:
        """Describe the problem."""
        super().__init__(
            f"User {user} has end date {end_date} later than start date {start_date}",
        )
