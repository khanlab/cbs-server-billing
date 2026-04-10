"""Quarter-end current-state snapshot utilities.

Snapshots capture the "current state" of users and projects as-of the
quarter-end date used for billing.  They are written as CSV files
alongside the existing billing artefacts, so that operators can inspect
the state without replaying the entire event log.

Output files
------------
``users_snapshot_<quarter_end>.csv``
    One row per active user as-of quarter end.  Columns:

    ``email``, ``name``, ``start_date``, ``end_date``,
    ``pi_name``, ``is_power_user``

``projects_snapshot_<quarter_end>.csv``
    One row per active project as-of quarter end.  Columns:

    ``email``, ``pi_last_name``, ``open_date``, ``close_date``,
    ``storage_tb``, ``speed_code``
"""

from __future__ import annotations

import datetime
import logging
import os
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from cbsserverbilling.spreadsheet.project import Project
from cbsserverbilling.spreadsheet.user import UpdateUser

logger = logging.getLogger(__name__)


def build_users_snapshot(
    users: Iterable[UpdateUser],
    quarter_end: datetime.date,
) -> pd.DataFrame:
    """Build a snapshot DataFrame of active users as-of *quarter_end*.

    Parameters
    ----------
    users
        Iterable of :class:`~cbsserverbilling.spreadsheet.user.UpdateUser`
        objects (e.g., from
        :func:`~cbsserverbilling.spreadsheet.user.enumerate_all_users`).
    quarter_end
        The last date of the billing quarter.

    Returns
    -------
    DataFrame
        Columns: ``email``, ``name``, ``start_date``, ``end_date``,
        ``pi_name``, ``is_power_user``.
    """
    rows = []
    for user in users:
        if not user.is_active(quarter_end):
            continue
        try:
            pi_name = user.get_pi_name(quarter_end)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Could not get pi_name for %s on %s: %s", user.email, quarter_end, exc,
            )
            pi_name = None
        try:
            is_power_user = user.is_power_user(quarter_end)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Could not get is_power_user for %s on %s: %s",
                user.email, quarter_end, exc,
            )
            is_power_user = None
        rows.append(
            {
                "email": user.email,
                "name": user.name,
                "start_date": user.start_date.isoformat(),
                "end_date": user.end_date.isoformat() if user.end_date else None,
                "pi_name": pi_name,
                "is_power_user": is_power_user,
            },
        )
    return pd.DataFrame(
        rows,
        columns=["email", "name", "start_date", "end_date", "pi_name", "is_power_user"],
    )


def build_projects_snapshot(
    projects: Iterable[Project],
    quarter_end: datetime.date,
) -> pd.DataFrame:
    """Build a snapshot DataFrame of active projects as-of *quarter_end*.

    Parameters
    ----------
    projects
        Iterable of :class:`~cbsserverbilling.spreadsheet.project.Project`
        objects (e.g., from
        :func:`~cbsserverbilling.spreadsheet.project.gen_all_projects`).
    quarter_end
        The last date of the billing quarter.

    Returns
    -------
    DataFrame
        Columns: ``email``, ``pi_last_name``, ``open_date``,
        ``close_date``, ``storage_tb``, ``speed_code``.
    """
    rows = []
    for project in projects:
        if not project.is_active(quarter_end):
            continue
        try:
            storage_tb = project.get_storage(quarter_end)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Could not get storage for %s on %s: %s",
                project.email, quarter_end, exc,
            )
            storage_tb = None
        try:
            speed_code = project.get_speed_code(quarter_end)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Could not get speed_code for %s on %s: %s",
                project.email, quarter_end, exc,
            )
            speed_code = None
        rows.append(
            {
                "email": project.email,
                "pi_last_name": project.pi_last_name,
                "open_date": project.open_date.isoformat(),
                "close_date": project.close_date.isoformat()
                if project.close_date
                else None,
                "storage_tb": storage_tb,
                "speed_code": speed_code,
            },
        )
    return pd.DataFrame(
        rows,
        columns=[
            "email",
            "pi_last_name",
            "open_date",
            "close_date",
            "storage_tb",
            "speed_code",
        ],
    )


def write_snapshots(
    users: Iterable[UpdateUser],
    projects: Iterable[Project],
    quarter_end: datetime.date,
    out_dir: os.PathLike[str] | str,
) -> tuple[Path, Path]:
    """Write user and project CSV snapshots to *out_dir*.

    Parameters
    ----------
    users
        Active users produced by the ingestion pipeline.
    projects
        Active projects produced by the ingestion pipeline.
    quarter_end
        The last date of the billing quarter (used in file names).
    out_dir
        Directory to write snapshot files into.

    Returns
    -------
    tuple[Path, Path]
        Paths to the written ``(users_snapshot, projects_snapshot)`` files.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    quarter_str = quarter_end.isoformat()
    users_file = out_path / f"users_snapshot_{quarter_str}.csv"
    projects_file = out_path / f"projects_snapshot_{quarter_str}.csv"

    users_df = build_users_snapshot(users, quarter_end)
    projects_df = build_projects_snapshot(projects, quarter_end)

    users_df.to_csv(users_file, index=False)
    projects_df.to_csv(projects_file, index=False)

    logger.info("Wrote users snapshot: %s (%d rows)", users_file, len(users_df))
    logger.info(
        "Wrote projects snapshot: %s (%d rows)", projects_file, len(projects_df),
    )

    return users_file, projects_file


def write_quarantine(
    quarantine_dfs: dict[str, pd.DataFrame],
    out_dir: os.PathLike[str] | str,
) -> list[Path]:
    """Write quarantine DataFrames to CSV files.

    Parameters
    ----------
    quarantine_dfs
        Mapping of ``{sheet_name: quarantine_df}`` where each value is a
        DataFrame containing invalid rows and a ``_quarantine_errors`` column.
    out_dir
        Directory to write quarantine files into.

    Returns
    -------
    list[Path]
        Paths to the written quarantine files (only non-empty ones).
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for sheet_name, qdf in quarantine_dfs.items():
        if qdf.empty:
            continue
        quarantine_file = out_path / f"quarantine_{sheet_name}.csv"
        qdf.to_csv(quarantine_file, index=False)
        logger.warning(
            "Quarantined %d row(s) from '%s' -> %s",
            len(qdf),
            sheet_name,
            quarantine_file,
        )
        written.append(quarantine_file)
    return written
