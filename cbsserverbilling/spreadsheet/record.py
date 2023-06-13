"""Module containing spreadsheet-based billing records."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Iterable
from pprint import pp

import pandas as pd
from attrs import define

from cbsserverbilling.dateutils import get_days_in_range
from cbsserverbilling.records import BillableProjectRecord, User
from cbsserverbilling.spreadsheet.project import Project, gen_all_projects
from cbsserverbilling.spreadsheet.user import (
    AccountUpdate,
    UpdateUser,
    enumerate_all_users,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@define
class SpreadsheetBillableProjectRecord(BillableProjectRecord):
    """Billable project record derived from a set of spreadsheets."""

    users: Iterable[UpdateUser]
    has_power_users: bool
    project: Project

    def get_pi_last_name(self) -> str:
        """Get the project PI's last name."""
        return self.project.pi_last_name

    def get_pi_full_name(self) -> str:
        """Get a PI's full name."""
        return self.project.pi_full_name or self.project.pi_last_name

    def get_storage_start(self) -> datetime.date:
        """Get a PI's storage start date."""
        return self.project.open_date

    def get_close_date(self) -> datetime.date | None:
        """Get a PI's account closure date, if any."""
        return self.project.close_date

    def get_storage_amount(self, date: datetime.date) -> float:
        """Get the amount of storage (in TB) allocated to this PI on a given date.

        Parameters
        ----------
        date
            Date to check storage price.
        """
        return self.project.get_storage(
            date,
        )

    def get_speed_code(self, date: datetime.date) -> str:
        """Get the speed code associated with this project on a date.

        Parameters
        ----------
        date
            Date on which to check the speed code.
        """
        return self.project.get_speed_code(date)

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
        days = get_days_in_range(start_date, end_date)
        return [
            user
            for user in self.users
            if any(
                (
                    user.is_active(date)
                    and (user.get_pi_name(date) == self.project.pi_last_name)
                )
                for date in days
            )
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
        if not self.has_power_users:
            return []
        days = get_days_in_range(start_date, end_date)
        return [
            user
            for user in self.users
            if any(
                (
                    user.is_active(date)
                    and (user.get_pi_name(date) == self.project.pi_last_name)
                    and user.is_power_user(date)
                )
                for date in days
            )
        ]


def gen_all_project_records(  # noqa: PLR0913
    user_df: pd.DataFrame,
    user_update_df: pd.DataFrame,
    pi_df: pd.DataFrame,
    pi_update_df: pd.DataFrame,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[SpreadsheetBillableProjectRecord]:
    """Generate a record for each project in the spreadsheets."""
    projects, user_requests = gen_all_projects(
        pi_df,
        pi_update_df,
        start_date,
        end_date,
    )
    users = enumerate_all_users(
        user_df,
        user_update_df,
        start_date,
        end_date,
        additional_requests=user_requests,
    )
    for project in projects:
        if project.close_date:
            print(project)
            users = AccountUpdate(
                timestamp=datetime.datetime.combine(
                    project.close_date,
                    datetime.time(),
                ),
                name=project.pi_last_name,
                email=project.email,
                end_date=project.close_date,
            ).handle(users)

    check_all_power_users(users, projects, start_date, end_date)
    print_all_power_users(users, start_date, end_date)

    used_pis = set()
    records = []
    for project in sorted(projects, key=lambda project: project.open_date):
        has_power_users = project.pi_last_name not in used_pis
        record = SpreadsheetBillableProjectRecord(
            project=project,
            has_power_users=has_power_users,
            users=users,
        )
        records.append(record)
        used_pis.add(project.pi_last_name)
    return records


def print_all_power_users(users: Iterable[User], start_date: datetime.date, end_date: datetime.date):
    days = get_days_in_range(start_date, end_date)
    for user in sorted(users, key=lambda user: user.name):
        if any((user.is_active(date) and user.is_power_user(date)) for date in days):
            pp(user)


def check_all_power_users(
    users: Iterable[User],
    projects: Iterable[Project],
    start_date: datetime.date,
    end_date: datetime.date,
) -> None:
    """Ensure that all power users are associated with a project."""
    days = get_days_in_range(start_date, end_date)
    all_pi_names = {project.pi_last_name for project in projects}
    for user in users:
        if any(
            (
                user.is_active(date)
                and (user.get_pi_name(date) not in all_pi_names)
                and user.is_power_user(date)
            )
            for date in days
        ):
            raise UnattachedUserError(user, start_date, end_date)


class UnattachedUserError(Exception):
    """Exception raised when a user has no active project."""

    def __init__(
        self,
        user: User,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> None:
        """Describe the problem."""
        super().__init__(
            f"User {user} has no real PI at some point from "
            f"{start_date.isoformat()} to {end_date.isoformat()}",
        )
