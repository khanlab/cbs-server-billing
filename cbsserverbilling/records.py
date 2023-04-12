"""Interface for getting raw CBS Server usage information."""

import datetime

from abc import ABCMeta, abstractmethod
from typing import Literal


class StorageRecord(metaclass=ABCMeta):
    """Record of a PI's account storage."""

    @abstractmethod
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

    @abstractmethod
    def get_storage_start(self, pi_last_name: str) -> datetime.date:
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
    def get_pi_account_close_date(self, pi_last_name: str) -> datetime.date | None:
        """Get a PI's account closure date, if any.

        Parameters
        ----------
        pi_last_name
            Last name of the PI.

        Returns
        -------
            Date this PI's account was closed, if any.
        """

    @abstractmethod
    def get_storage_amount(self, pi_last_name: str, date: datetime.date) -> float:
        """Get the amount of storage allocated to this PI on a given date.

        Parameters
        ----------
        pi_last_name
            Last name of the PI.
        date
            Date to check storage price.

        Returns
        -------
            Amount of storage (in TB) allocated to this PI.
        """

    @abstractmethod
    def get_speed_code(self, pi_last_name: str, date: datetime.date) -> str:
        """Get the speed code associated with this PI on a date.

        Parameters
        ----------
        pi_last_name
            Last name of the PI.
        date
            Date on which to check the speed code.

        Returns
        -------
            Speed code associated with this PI.
        """


class PowerUsersRecord(metaclass=ABCMeta):
    """Record describing the CBS Servers' power users."""

    @abstractmethod
    def enumerate_all_users(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[tuple[str, datetime.date, datetime.date]]:
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
        self, pi_last_name: str, start_date: datetime.date, end_date: datetime.date
    ) -> list[tuple[str, datetime.date, datetime.date]]:
        """Generate a list of power users associated with this PI.

        Parameters
        ----------
        pi_last_name
            PI of the users to enumerate.
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
    ) -> list[
        tuple[Literal[True], datetime.date, datetime.date]
        | tuple[Literal[False], None, None]
    ]:
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
