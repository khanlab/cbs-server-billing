"""Tests for cbsserverbilling.snapshot."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from cbsserverbilling.snapshot import (
    build_projects_snapshot,
    build_users_snapshot,
    write_quarantine,
    write_snapshots,
)
from cbsserverbilling.spreadsheet.project import Project, ProjectUpdate
from cbsserverbilling.spreadsheet.user import Update, UpdateUser
from cbsserverbilling.validation import QUARANTINE_COL

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

QUARTER_END = datetime.date(2021, 1, 31)
QUARTER_START = datetime.date(2020, 11, 1)


def _make_user(
    email: str,
    name: str,
    start: datetime.date,
    end: datetime.date | None,
    pi_name: str,
    power_user: bool,
) -> UpdateUser:
    return UpdateUser(
        email=email,
        name=name,
        start_date=start,
        end_date=end,
        updates=frozenset(
            [
                Update(
                    date=start,
                    pi_name=pi_name,
                    power_user=power_user,
                ),
            ],
        ),
    )


def _make_project(
    email: str,
    pi_last_name: str,
    open_date: datetime.date,
    close_date: datetime.date | None,
    speed_code: str,
    storage: float,
) -> Project:
    return Project(
        email=email,
        pi_last_name=pi_last_name,
        open_date=open_date,
        close_date=close_date,
        updates=frozenset(
            [
                ProjectUpdate(
                    date=open_date,
                    speed_code=speed_code,
                    additional_storage=storage,
                ),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# build_users_snapshot
# ---------------------------------------------------------------------------


class TestBuildUsersSnapshot:
    def test_columns_present(self):
        user = _make_user(
            "a@example.com", "Apple", datetime.date(2020, 1, 1), None, "Smith", False,
        )
        df = build_users_snapshot([user], QUARTER_END)
        assert set(df.columns) == {"email", "name", "start_date", "end_date", "pi_name", "is_power_user"}

    def test_active_user_included(self):
        user = _make_user(
            "a@example.com", "Apple", datetime.date(2020, 1, 1), None, "Smith", False,
        )
        df = build_users_snapshot([user], QUARTER_END)
        assert len(df) == 1
        assert df.iloc[0]["email"] == "a@example.com"

    def test_inactive_user_excluded(self):
        user = _make_user(
            "a@example.com", "Apple", datetime.date(2020, 1, 1),
            datetime.date(2020, 6, 30), "Smith", False,
        )
        df = build_users_snapshot([user], QUARTER_END)
        assert df.empty

    def test_multiple_users(self):
        users = [
            _make_user("a@example.com", "Apple", datetime.date(2020, 1, 1), None, "Smith", False),
            _make_user("b@example.com", "Banana", datetime.date(2020, 2, 1), None, "Jones", True),
        ]
        df = build_users_snapshot(users, QUARTER_END)
        assert len(df) == 2

    def test_end_date_serialized(self):
        user = _make_user(
            "a@example.com", "Apple", datetime.date(2020, 1, 1),
            datetime.date(2021, 6, 30), "Smith", False,
        )
        df = build_users_snapshot([user], QUARTER_END)
        assert df.iloc[0]["end_date"] == "2021-06-30"

    def test_no_end_date_is_none(self):
        user = _make_user("a@example.com", "Apple", datetime.date(2020, 1, 1), None, "Smith", False)
        df = build_users_snapshot([user], QUARTER_END)
        assert df.iloc[0]["end_date"] is None

    def test_empty_input_produces_empty_df(self):
        df = build_users_snapshot([], QUARTER_END)
        assert df.empty
        assert list(df.columns) == ["email", "name", "start_date", "end_date", "pi_name", "is_power_user"]

    def test_power_user_flag(self):
        user = _make_user("a@example.com", "Apple", datetime.date(2020, 1, 1), None, "Smith", True)
        df = build_users_snapshot([user], QUARTER_END)
        assert df.iloc[0]["is_power_user"]


# ---------------------------------------------------------------------------
# build_projects_snapshot
# ---------------------------------------------------------------------------


class TestBuildProjectsSnapshot:
    def test_columns_present(self):
        project = _make_project(
            "pi@example.com", "Smith", datetime.date(2020, 1, 1), None, "AAAA", 10.0,
        )
        df = build_projects_snapshot([project], QUARTER_END)
        assert set(df.columns) == {"email", "pi_last_name", "open_date", "close_date", "storage_tb", "speed_code"}

    def test_active_project_included(self):
        project = _make_project(
            "pi@example.com", "Smith", datetime.date(2020, 1, 1), None, "AAAA", 10.0,
        )
        df = build_projects_snapshot([project], QUARTER_END)
        assert len(df) == 1

    def test_closed_project_excluded(self):
        project = _make_project(
            "pi@example.com", "Smith", datetime.date(2020, 1, 1),
            datetime.date(2020, 6, 30), "AAAA", 10.0,
        )
        df = build_projects_snapshot([project], QUARTER_END)
        assert df.empty

    def test_storage_and_speed_code(self):
        project = _make_project(
            "pi@example.com", "Smith", datetime.date(2020, 1, 1), None, "ZZZZ", 5.0,
        )
        df = build_projects_snapshot([project], QUARTER_END)
        assert df.iloc[0]["storage_tb"] == 5.0
        assert df.iloc[0]["speed_code"] == "ZZZZ"  # snapshot preserves case from Project object

    def test_empty_input_produces_empty_df(self):
        df = build_projects_snapshot([], QUARTER_END)
        assert df.empty
        assert list(df.columns) == ["email", "pi_last_name", "open_date", "close_date", "storage_tb", "speed_code"]


# ---------------------------------------------------------------------------
# write_snapshots
# ---------------------------------------------------------------------------


class TestWriteSnapshots:
    def test_files_created(self, tmp_path: Path):
        user = _make_user("a@example.com", "Apple", datetime.date(2020, 1, 1), None, "Smith", False)
        project = _make_project("pi@example.com", "Smith", datetime.date(2020, 1, 1), None, "AAAA", 10.0)

        users_file, projects_file = write_snapshots([user], [project], QUARTER_END, tmp_path)

        assert users_file.exists()
        assert projects_file.exists()

    def test_file_names_contain_quarter_end(self, tmp_path: Path):
        users_file, projects_file = write_snapshots([], [], QUARTER_END, tmp_path)
        assert "2021-01-31" in users_file.name
        assert "2021-01-31" in projects_file.name

    def test_csv_format(self, tmp_path: Path):
        import pandas as pd

        user = _make_user("a@example.com", "Apple", datetime.date(2020, 1, 1), None, "Smith", False)
        users_file, _ = write_snapshots([user], [], QUARTER_END, tmp_path)

        df = pd.read_csv(users_file)
        assert "email" in df.columns
        assert len(df) == 1

    def test_out_dir_created_if_missing(self, tmp_path: Path):
        out_dir = tmp_path / "nested" / "subdir"
        write_snapshots([], [], QUARTER_END, out_dir)
        assert out_dir.exists()

    def test_row_counts_match(self, tmp_path: Path):
        import pandas as pd

        users = [
            _make_user("a@example.com", "Apple", datetime.date(2020, 1, 1), None, "Smith", False),
            _make_user("b@example.com", "Banana", datetime.date(2020, 2, 1), None, "Jones", True),
        ]
        projects = [
            _make_project("pi@example.com", "Smith", datetime.date(2020, 1, 1), None, "AAAA", 10.0),
        ]
        users_file, projects_file = write_snapshots(users, projects, QUARTER_END, tmp_path)

        users_df = pd.read_csv(users_file)
        projects_df = pd.read_csv(projects_file)
        assert len(users_df) == 2
        assert len(projects_df) == 1


# ---------------------------------------------------------------------------
# write_quarantine
# ---------------------------------------------------------------------------


class TestWriteQuarantine:
    def test_empty_quarantine_no_files_written(self, tmp_path: Path):
        import pandas as pd

        empty = pd.DataFrame()
        written = write_quarantine({"pi_form": empty}, tmp_path)
        assert written == []

    def test_non_empty_quarantine_written(self, tmp_path: Path):
        import pandas as pd

        qdf = pd.DataFrame(
            [{"email": "bad", "last_name": "X", QUARANTINE_COL: "column 'email': bad"}],
        )
        written = write_quarantine({"pi_form": qdf}, tmp_path)
        assert len(written) == 1
        assert written[0].name == "quarantine_pi_form.csv"

    def test_quarantine_file_content(self, tmp_path: Path):
        import pandas as pd

        qdf = pd.DataFrame(
            [{"email": "bad", "last_name": "X", QUARANTINE_COL: "some error"}],
        )
        write_quarantine({"user_form": qdf}, tmp_path)
        result = pd.read_csv(tmp_path / "quarantine_user_form.csv")
        assert QUARANTINE_COL in result.columns
        assert result.iloc[0][QUARANTINE_COL] == "some error"

    def test_only_non_empty_sheets_written(self, tmp_path: Path):
        import pandas as pd

        empty = pd.DataFrame()
        qdf = pd.DataFrame([{"email": "bad", QUARANTINE_COL: "err"}])
        written = write_quarantine({"empty_sheet": empty, "real_sheet": qdf}, tmp_path)
        assert len(written) == 1
        assert "real_sheet" in written[0].name
