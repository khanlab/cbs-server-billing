"""Interface for getting raw CBS Server usage information."""

import datetime
from abc import ABCMeta, abstractmethod

from attrs import define


@define
class User:
    """A user of the CBS Server."""
    # pylint: disable=too-few-public-methods
    name: str
    power_user: bool
    start_date: datetime.date
    end_date: datetime.date | None = None


class BillableProjectRecord(metaclass=ABCMeta):
    """Record of one billable project."""

    @abstractmethod
    def get_pi_full_name(self) -> str:
        """Get a PI's full name.

        Returns
        -------
        Full name of the PI
        """

    @abstractmethod
    def get_storage_start(self) -> datetime.date:
        """Get a PI's storage start date.

        Parameters
        ----------
        pi_last_name
            Last name of the PI.

        Returns
        -------
            Date this PI's storage started.
        """

    @abstractmethod
    def get_close_date(self) -> datetime.date | None:
        """Get a PI's account closure date, if any.

        Returns
        -------
            Date this PI's account was closed, if any.
        """

    @abstractmethod
    def get_storage_amount(self, date: datetime.date) -> float:
        """Get the amount of storage allocated to this PI on a given date.

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

        Returns
        -------
            Speed code associated with this PI.
        """

    @abstractmethod
    def enumerate_all_users(
        self, start_date: datetime.date, end_date: datetime.date
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
            A tuple for each user who was active on any day in the given
            range. The tuple contains the user's name, start date, and end
            date.
        """

    @abstractmethod
    def enumerate_power_users(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[User]:
        """Generate a list of power users associated with this PI.

        Parameters
        ----------
        start_date
            First date to consider.
        end_date
            Last date to consider.

        Returns
        -------
            A namedtuple for each user who was active on any day in the given
            range, where each namedtuple contains the user's last name, start
            date, and end date, in that order.
        """

    @abstractmethod
    def describe_user(
        self, last_name: str, period_start: datetime.date, period_end: datetime.date
    ) -> list[User]:
        """Check whether a user was a power user in a given period.

        Parameters
        ----------
        last_name
            The user's last name.
        period_start
            First day of the period to check.
        period_end
            Last day of the period to check.

        Returns
        -------
            Tuples describing whether the user was a power user during each
            of their terms during the period, then if so, the start and end
            dates of those terms.
        """
