"""Module handling PI account details."""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import NamedTuple

import pandas as pd
from attrs import Attribute, define, evolve, field
from typing_extensions import Self


@define(frozen=True)
class ProjectUpdate:
    """Update to a project."""

    date: datetime.date
    speed_code: str | None
    storage: float | None


class InvalidProjectError(Exception):
    """Exception raised when a user is misspecified."""

    def __init__(self, project: Project, missing_attrs: str) -> None:
        """Information about the misspecified user."""
        super().__init__(f"Project {project} is missing required info {missing_attrs}")


def _both_defined(
    instance: Project,
    _: Attribute[frozenset[ProjectUpdate]],
    value: frozenset[ProjectUpdate],
) -> None:
    if not [update for update in value if update.storage is not None]:
        raise InvalidProjectError(instance, "storage")
    if not [update for update in value if update.speed_code]:
        raise InvalidProjectError(instance, "speed code")


@define(frozen=True)
class Project:
    """One project."""

    open_date: datetime.date
    email: str
    pi_last_name: str
    close_date: datetime.date | None = None
    updates: frozenset[ProjectUpdate] = field(
        default=frozenset(),
        validator=[_both_defined],
    )


class NewPiTuple(NamedTuple):
    """Tuple describing a new PI account request from pandas."""

    start_timestamp: pd.Timestamp
    email: pd.StringDtype
    last_name: pd.StringDtype
    speed_code: pd.StringDtype
    storage: float


@define
class NewPiRequest:
    """Dataclass describing a new PI request."""

    timestamp: datetime.datetime
    name: str
    email: str
    speed_code: str
    storage: float

    @classmethod
    def from_pd_tuple(cls, tuple_: NewPiTuple) -> Self:
        """Generate a request from a pandas tuple."""
        return cls(
            timestamp=tuple_.start_timestamp.to_pydatetime(),
            name=str(tuple_.last_name),
            email=str(tuple_.email),
            speed_code=str(tuple_.speed_code),
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
                            storage=self.storage,
                        ),
                    },
                ),
            ),
        ]


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
        if len(candidates) == 1:
            to_update = candidates[0]
        return list(set(projects) - {candidates[0]} | {evolve(to_update)})
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
                            storage=self.storage,
                        ),
                    },
                ),
            ),
        ]


def gen_all_projects(
    pi_df: pd.DataFrame,
    pi_update_df: pd.DataFrame,
    start_date: datetime.date,
    end_date: datetime.date,
) -> None:
    changes = [
        NewPiRequest.from_pd_tuple(tuple_)
        for tuple_ in pi_df.loc[
            pi_df["start_timestamp"].dt.date <= end_date,
            ["start_timestamp", "email", "last_name", "speed_code", "storage"],
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
    for change in sorted(changes, key=lambda change: change.timestamp):
        print(change)
