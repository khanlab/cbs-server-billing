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
    ) -> list[User]:
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
    ) -> list[User]:
        """Generate a list of power users associated with this PI.

        Parameters
        ----------
        start_date
            First date to consider.
        end_date
            Last date to consider.
        """

    @abstractmethod
    def describe_user(
        self,
        last_name: str,
        period_start: datetime.date,
        period_end: datetime.date,
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
        list[User]
            A User for each term for which a user was active during the given period.
        """
