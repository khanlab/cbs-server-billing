"""Module handling PI account details."""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import NamedTuple

import pandas as pd
from attrs import Attribute, define, evolve, field
from typing_extensions import Self

from cbsserverbilling.spreadsheet.user import AccountRequest, AccountUpdate


@define(frozen=True)
class ProjectUpdate:
    """Update to a project."""

    date: datetime.date
    speed_code: str | None
    additional_storage: float | None


def _both_defined(
    instance: Project,
    _: Attribute[frozenset[ProjectUpdate]],
    value: frozenset[ProjectUpdate],
) -> None:
    if not [update for update in value if update.additional_storage is not None]:
        raise InvalidProjectError(instance, "additional_storage")
    if not [update for update in value if update.speed_code]:
        raise InvalidProjectError(instance, "speed code")


@define(frozen=True)
class Project:
    """One project."""

    open_date: datetime.date
    email: str
    pi_last_name: str
    pi_full_name: str | None = None
    close_date: datetime.date | None = None
    updates: frozenset[ProjectUpdate] = field(
        default=frozenset(),
        validator=[_both_defined],
    )

    def is_active(self, date: datetime.date) -> bool:
        """Check if the project was active on a date."""
        return (date >= self.open_date) and (
            (not self.close_date) or date <= self.close_date
        )

    def check_valid_date(self, date: datetime.date) -> None:
        """Raise an exception if the project wasn't active on a date."""
        if not self.is_active(date):
            raise InactiveProjectError(self, date)

    def get_storage(self, date: datetime.date) -> float:
        """Check a project's storage on this date."""
        self.check_valid_date(date)
        return sum(
            update.additional_storage
            for update in self.updates
            if (update.date <= date) and update.additional_storage
        )

    def get_speed_code(self, date: datetime.date) -> str:
        """Check a project's speed code on this date."""
        self.check_valid_date(date)
        return max(  # type: ignore[reportGeneralTypeIssues]
            (update for update in self.updates if update.speed_code),
            key=lambda update: update.date,
        ).speed_code


class NewPiTuple(NamedTuple):
    """Tuple describing a new PI account request from pandas."""

    start_timestamp: pd.Timestamp
    email: pd.StringDtype
    last_name: pd.StringDtype
    speed_code: pd.StringDtype
    pi_is_power_user: bool
    storage: float


@define
class NewPiRequest:
    """Dataclass describing a new PI request."""

    timestamp: datetime.datetime
    name: str
    email: str
    speed_code: str
    power_user: bool
    storage: float

    @classmethod
    def from_pd_tuple(cls, tuple_: NewPiTuple) -> Self:
        """Generate a request from a pandas tuple."""
        return cls(
            timestamp=tuple_.start_timestamp.to_pydatetime(),
            name=str(tuple_.last_name),
            email=str(tuple_.email),
            speed_code=str(tuple_.speed_code),
            power_user=bool(tuple_.pi_is_power_user),
            storage=float(tuple_.storage),
        )

    def handle(self, projects: Iterable[Project]) -> list[Project]:
        """Update a list of projects with this."""
        return [
            *projects,
            Project(
                open_date=self.timestamp.date(),
                pi_last_name=self.name,
                email=self.email,
                updates=frozenset(
                    {
                        ProjectUpdate(
                            date=self.timestamp.date(),
                            speed_code=self.speed_code,
                            additional_storage=self.storage,
                        ),
                    },
                ),
            ),
        ]

    def gen_user_request(self) -> AccountRequest:
        """Generate an account request corresponding to this PI."""
        return AccountRequest(
            timestamp=self.timestamp,
            name=self.name,
            email=self.email,
            pi_name=self.name,
            power_user=self.power_user,
            end_date=None,
        )


class PiUpdateTuple(NamedTuple):
    """Tuple describing a new PI account request from pandas."""

    timestamp: pd.Timestamp
    email: pd.StringDtype
    last_name: pd.StringDtype
    speed_code: str
    new_storage: float
    account_closed: bool


@define
class PiUpdate:
    """A requested update to a PI account."""

    timestamp: datetime.datetime
    email: str
    name: str
    speed_code: str | None
    additional_storage: float | None
    account_closed: bool | None

    @classmethod
    def from_pd_tuple(cls, tuple_: PiUpdateTuple) -> Self:
        """Generate an update from a pandas tuple."""
        return cls(
            timestamp=tuple_.timestamp.to_pydatetime(),
            name=str(tuple_.last_name),
            email=str(tuple_.email),
            speed_code=str(tuple_.speed_code) if pd.notna(tuple_.speed_code) else None,
            additional_storage=float(tuple_.new_storage)
            if pd.notna(tuple_.new_storage)
            else None,
            account_closed=bool(tuple_.account_closed)
            if pd.notna(tuple_.account_closed)
            else None,
        )

    def handle(self, projects: Iterable[Project]) -> list[Project]:
        """Update a list of projects with this."""
        candidates = [
            project for project in projects if project.pi_last_name == self.name
        ]
        if not candidates:
            raise InvalidPiUpdateError(self)
        to_update = (
            candidates[0]
            if len(candidates) == 1
            else min(candidates, key=lambda project: project.open_date)
        )

        new_end_date = (
            {"close_date": self.timestamp.date()} if self.account_closed else {}
        )
        return list(
            set(projects) - {to_update}
            | {
                evolve(
                    to_update,
                    updates=to_update.updates
                    | frozenset(
                        [
                            ProjectUpdate(
                                date=self.timestamp.date(),
                                additional_storage=self.additional_storage,
                                speed_code=self.speed_code,
                            ),
                        ],
                    ),
                    **new_end_date,
                ),
            },
        )

    def gen_user_request(self) -> AccountUpdate | None:
        """Generate an account request corresponding to this PI."""
        if not self.account_closed:
            return None
        return AccountUpdate(
            timestamp=self.timestamp,
            name=self.name,
            email=self.email,
            end_date=self.timestamp.date(),
        )


def gen_all_projects(
    pi_df: pd.DataFrame,
    pi_update_df: pd.DataFrame,
    start_date: datetime.date,
    end_date: datetime.date,
) -> tuple[list[Project], Iterable[AccountRequest | AccountUpdate]]:
    """Generate all projects defined in a period."""
    changes = [
        NewPiRequest.from_pd_tuple(tuple_)
        for tuple_ in pi_df.loc[
            pi_df["start_timestamp"].dt.date <= end_date,
            [
                "start_timestamp",
                "email",
                "last_name",
                "speed_code",
                "storage",
                "pi_is_power_user",
            ],
        ].itertuples()
    ] + [
        PiUpdate.from_pd_tuple(tuple_)
        for tuple_ in pi_update_df.loc[
            pi_update_df["timestamp"].dt.date <= end_date,
            [
                "timestamp",
                "email",
                "last_name",
                "speed_code",
                "new_storage",
                "account_closed",
            ],
        ].itertuples()
    ]
    projects: list[Project] = []
    for change in sorted(changes, key=lambda change: change.timestamp):
        projects = change.handle(projects)

    user_changes = [
        update for change in changes if (update := change.gen_user_request())
    ]

    return [
        project
        for project in projects
        if ((not project.close_date) or (project.close_date >= start_date))
    ], user_changes


class InvalidProjectError(Exception):
    """Exception raised when a user is misspecified."""

    def __init__(self, project: Project, missing_attrs: str) -> None:
        """Information about the misspecified user."""
        super().__init__(f"Project {project} is missing required info {missing_attrs}")


class InactiveProjectError(Exception):
    """Exception raised when a project is operated on while inactive."""

    def __init__(self, project: Project, date: datetime.date) -> None:
        """Information about the inactive project."""
        super().__init__(f"Project {project} is inactive on date {date}")


class InvalidPiUpdateError(Exception):
    """Exception raised when a PI update has no corresponding PI."""

    def __init__(self, update: PiUpdate) -> None:
        """Information about the misspecified update."""
        super().__init__(
            f"There is no PI account with the last name of PI update {update}.",
        )
