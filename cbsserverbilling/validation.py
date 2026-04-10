"""Validation and quarantine layer for spreadsheet ingestion.

This module provides row-level validation for each input sheet and
quarantine behaviour: invalid rows are separated into a quarantine
DataFrame (with error messages) while the rest of the pipeline proceeds
using only the validated rows.

Critical failures (e.g. missing required columns after renaming) raise
``ColumnError`` immediately, because the pipeline cannot continue
without them.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pandas as pd

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

# Basic email sanity check: requires <local>@<domain>.<tld>.  Does not
# enforce RFC-5321 details (valid TLDs, hyphen rules, etc.) - the goal is
# to catch obviously missing or blank email addresses, not to act as a
# full RFC validator.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

QUARANTINE_COL = "_quarantine_errors"


class ColumnError(ValueError):
    """Raised when a required column is missing after renaming."""

    def __init__(self, sheet: str, missing: list[str]) -> None:
        """Describe the missing-column error."""
        cols = ", ".join(missing)
        super().__init__(
            f"Sheet '{sheet}' is missing required columns after renaming: {cols}. "
            "Cannot continue.",
        )
        self.sheet = sheet
        self.missing = missing


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_columns(df: pd.DataFrame, required: list[str], sheet: str) -> None:
    """Raise ColumnError if any required columns are absent."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ColumnError(sheet, missing)


def _excel_row(pd_index: object) -> int:
    """Convert a zero-based pandas integer index to an Excel row number.

    Excel rows start at 1 (header) so data begins at row 2.
    """
    return int(pd_index) + 2


def _is_valid_email(value: object) -> bool:
    return isinstance(value, str) and bool(_EMAIL_RE.match(value))


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_valid_timestamp(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, pd.Timestamp):
        return True
    try:
        pd.Timestamp(value)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return False
    else:
        return True


def _is_nonneg_number(value: object) -> bool:
    if pd.isna(value):
        return False
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False


def _is_bool_like(value: object) -> bool:
    """Return True if value is already a bool or a bool-equivalent."""
    return isinstance(value, bool | int) or (
        isinstance(value, str)
        and value.strip().lower() in {"true", "false", "yes", "no", "0", "1"}
    )


# ---------------------------------------------------------------------------
# Row validator factories
# ---------------------------------------------------------------------------

RowErrors = list[str]
RowValidator = Callable[[pd.Series], RowErrors]  # type: ignore[type-arg]


def _validate_row(
    row: pd.Series,  # type: ignore[type-arg]
    checks: list[tuple[str, Callable[[object], bool], str]],
) -> RowErrors:
    """Run a list of (column, check_fn, error_message) checks on one row.

    Parameters
    ----------
    row
        A pandas Series representing a single data row.
    checks
        Each entry is ``(column_name, predicate, message_suffix)``.
        The full error message will be:
        ``"column '<col>': <message_suffix> (Excel row <n>)"``.
    """
    errors: RowErrors = []
    for col, check, msg in checks:
        if col not in row.index:
            continue
        if not check(row[col]):
            errors.append(
                f"column '{col}': {msg} (Excel row {_excel_row(row.name)})",
            )
    return errors


# ---------------------------------------------------------------------------
# Per-sheet validation
# ---------------------------------------------------------------------------

_USER_DF_REQUIRED = [
    "start_timestamp", "email", "last_name", "pi_last_name", "power_user",
]
_USER_UPDATE_DF_REQUIRED = ["timestamp", "email", "last_name"]
_PI_DF_REQUIRED = [
    "start_timestamp", "email", "last_name",
    "speed_code", "storage", "pi_is_power_user",
]
_STORAGE_UPDATE_DF_REQUIRED = ["timestamp", "email", "last_name"]


def validate_user_df(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate a user-form DataFrame (post-rename).

    Parameters
    ----------
    df
        DataFrame produced by :func:`~cbsserverbilling.spreadsheet.io.load_user_df`.

    Returns
    -------
    tuple[DataFrame, DataFrame]
        ``(valid_df, quarantine_df)`` where *quarantine_df* contains all
        invalid rows plus an extra ``_quarantine_errors`` column.

    Raises
    ------
    ColumnError
        If a required column is missing entirely.
    """
    _require_columns(df, _USER_DF_REQUIRED, "user_form")

    checks: list[tuple[str, Callable[[object], bool], str]] = [
        ("email", _is_valid_email, "must be a non-empty email address"),
        ("start_timestamp", _is_valid_timestamp, "must be a parseable timestamp"),
        ("last_name", _is_nonempty_str, "must be a non-empty string"),
        ("pi_last_name", _is_nonempty_str, "must be a non-empty string"),
        ("power_user", _is_bool_like, "must be a boolean-like value"),
    ]
    return _split_valid_quarantine(df, checks)


def validate_user_update_df(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate a user-update-form DataFrame (post-rename).

    Parameters
    ----------
    df
        DataFrame produced by
        :func:`~cbsserverbilling.spreadsheet.io.load_user_update_df`.

    Returns
    -------
    tuple[DataFrame, DataFrame]
    """
    _require_columns(df, _USER_UPDATE_DF_REQUIRED, "user_update_form")

    checks: list[tuple[str, Callable[[object], bool], str]] = [
        ("email", _is_valid_email, "must be a non-empty email address"),
        ("timestamp", _is_valid_timestamp, "must be a parseable timestamp"),
        ("last_name", _is_nonempty_str, "must be a non-empty string"),
    ]
    return _split_valid_quarantine(df, checks)


def validate_pi_df(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate a PI-form DataFrame (post-rename).

    Parameters
    ----------
    df
        DataFrame produced by :func:`~cbsserverbilling.spreadsheet.io.load_pi_df`.

    Returns
    -------
    tuple[DataFrame, DataFrame]
    """
    _require_columns(df, _PI_DF_REQUIRED, "pi_form")

    checks: list[tuple[str, Callable[[object], bool], str]] = [
        ("email", _is_valid_email, "must be a non-empty email address"),
        ("start_timestamp", _is_valid_timestamp, "must be a parseable timestamp"),
        ("last_name", _is_nonempty_str, "must be a non-empty string"),
        ("speed_code", _is_nonempty_str, "must be a non-empty speed code"),
        ("storage", _is_nonneg_number, "must be a non-negative number"),
        ("pi_is_power_user", _is_bool_like, "must be a boolean-like value"),
    ]
    return _split_valid_quarantine(df, checks)


def validate_storage_update_df(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate a storage-update-form DataFrame (post-rename).

    Parameters
    ----------
    df
        DataFrame produced by
        :func:`~cbsserverbilling.spreadsheet.io.load_storage_update_df`.

    Returns
    -------
    tuple[DataFrame, DataFrame]
    """
    _require_columns(df, _STORAGE_UPDATE_DF_REQUIRED, "storage_update_form")

    checks: list[tuple[str, Callable[[object], bool], str]] = [
        ("email", _is_valid_email, "must be a non-empty email address"),
        ("timestamp", _is_valid_timestamp, "must be a parseable timestamp"),
        ("last_name", _is_nonempty_str, "must be a non-empty string"),
    ]

    # Also validate new_storage if the column exists and the cell is not NA
    def _optional_storage(value: object) -> bool:
        if pd.isna(value):
            return True  # Optional field; NA is OK
        return _is_nonneg_number(value)

    if "new_storage" in df.columns:
        checks.append(
            (
                "new_storage",
                _optional_storage,
                "when provided, must be a non-negative number",
            ),
        )

    return _split_valid_quarantine(df, checks)


# ---------------------------------------------------------------------------
# Core split logic
# ---------------------------------------------------------------------------


def _split_valid_quarantine(
    df: pd.DataFrame,
    checks: list[tuple[str, Callable[[object], bool], str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply row-level checks and split df into (valid, quarantine)."""
    error_lists: list[str] = []
    for _, row in df.iterrows():
        errs = _validate_row(row, checks)
        error_lists.append("; ".join(errs))

    error_series = pd.Series(error_lists, index=df.index)
    is_invalid = error_series.str.len() > 0

    valid_df = df.loc[~is_invalid].copy()
    quarantine_df = df.loc[is_invalid].copy()
    quarantine_df[QUARANTINE_COL] = error_series.loc[is_invalid]

    return valid_df.reset_index(drop=True), quarantine_df.reset_index(drop=True)

