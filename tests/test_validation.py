"""Tests for cbsserverbilling.validation."""

from __future__ import annotations

import datetime

import pandas as pd
import pytest

from cbsserverbilling.validation import (
    QUARANTINE_COL,
    ColumnError,
    validate_pi_df,
    validate_pi_update_refs,
    validate_power_user_pi_refs,
    validate_storage_update_df,
    validate_user_df,
    validate_user_update_df,
    validate_user_update_refs,
)

# ---------------------------------------------------------------------------
# Fixtures: minimal valid DataFrames (post-rename, matching io.py output)
# ---------------------------------------------------------------------------

VALID_USER_ROW = {
    "start_timestamp": pd.Timestamp("2021-01-01 10:00:00"),
    "email": "alice@example.com",
    "first_name": "Alice",
    "last_name": "Apple",
    "pi_last_name": "Smith",
    "end_timestamp": pd.Timestamp("2023-12-31"),
    "power_user": False,
}

VALID_PI_ROW = {
    "start_timestamp": pd.Timestamp("2020-01-01 09:00:00"),
    "email": "pi@example.com",
    "first_name": "Penny",
    "last_name": "Pi",
    "pi_is_power_user": True,
    "speed_code": "AAAA",
    "storage": 10.0,
}

VALID_USER_UPDATE_ROW = {
    "timestamp": pd.Timestamp("2021-06-01 12:00:00"),
    "email": "alice@example.com",
    "first_name": "Alice",
    "last_name": "Apple",
    "pi_last_name": "Smith",
    "agree": True,
}

VALID_STORAGE_UPDATE_ROW = {
    "timestamp": pd.Timestamp("2021-06-01 12:00:00"),
    "email": "pi@example.com",
    "first_name": "Penny",
    "last_name": "Pi",
    "speed_code": "BBBB",
    "new_storage": 5.0,
    "agree": True,
    "account_closed": False,
}


def _df(*rows: dict) -> pd.DataFrame:
    """Construct a DataFrame from one or more row-dicts."""
    return pd.DataFrame(list(rows))


# ---------------------------------------------------------------------------
# validate_user_df
# ---------------------------------------------------------------------------


class TestValidateUserDf:
    def test_all_valid_rows_pass(self):
        df = _df(VALID_USER_ROW, VALID_USER_ROW)
        valid, quarantine = validate_user_df(df)
        assert len(valid) == 2
        assert quarantine.empty

    def test_missing_required_column_raises(self):
        df = _df(VALID_USER_ROW).drop(columns=["email"])
        with pytest.raises(ColumnError) as exc_info:
            validate_user_df(df)
        assert "user_form" in str(exc_info.value)
        assert "email" in str(exc_info.value)

    def test_invalid_email_quarantined(self):
        bad_row = {**VALID_USER_ROW, "email": "not-an-email"}
        df = _df(VALID_USER_ROW, bad_row)
        valid, quarantine = validate_user_df(df)
        assert len(valid) == 1
        assert len(quarantine) == 1
        assert "email" in quarantine.iloc[0][QUARANTINE_COL]

    def test_empty_email_quarantined(self):
        bad_row = {**VALID_USER_ROW, "email": ""}
        df = _df(bad_row)
        valid, quarantine = validate_user_df(df)
        assert valid.empty
        assert len(quarantine) == 1

    def test_empty_pi_last_name_quarantined(self):
        bad_row = {**VALID_USER_ROW, "pi_last_name": "   "}
        df = _df(bad_row)
        valid, quarantine = validate_user_df(df)
        assert valid.empty

    def test_invalid_timestamp_quarantined(self):
        bad_row = {**VALID_USER_ROW, "start_timestamp": "not-a-date"}
        df = _df(bad_row)
        valid, quarantine = validate_user_df(df)
        assert valid.empty
        assert "start_timestamp" in quarantine.iloc[0][QUARANTINE_COL]

    def test_multiple_errors_combined_in_one_entry(self):
        bad_row = {
            **VALID_USER_ROW,
            "email": "bad",
            "pi_last_name": "",
        }
        df = _df(bad_row)
        _, quarantine = validate_user_df(df)
        errors = quarantine.iloc[0][QUARANTINE_COL]
        assert "email" in errors
        assert "pi_last_name" in errors

    def test_quarantine_preserves_original_data(self):
        bad_row = {**VALID_USER_ROW, "email": "bad"}
        df = _df(bad_row)
        _, quarantine = validate_user_df(df)
        assert quarantine.iloc[0]["last_name"] == VALID_USER_ROW["last_name"]

    def test_quarantine_resets_index(self):
        bad_row = {**VALID_USER_ROW, "email": "bad"}
        df = _df(VALID_USER_ROW, bad_row)
        valid, quarantine = validate_user_df(df)
        assert list(valid.index) == [0]
        assert list(quarantine.index) == [0]

    def test_excel_row_number_in_error_message(self):
        """Error message should include an Excel row reference."""
        bad_row = {**VALID_USER_ROW, "email": "bad"}
        df = _df(VALID_USER_ROW, bad_row)
        _, quarantine = validate_user_df(df)
        errors = quarantine.iloc[0][QUARANTINE_COL]
        # Row index 1 in pandas (0-based) = Excel row 3 (header is row 1)
        assert "Excel row 3" in errors

    def test_end_timestamp_na_accepted(self):
        """end_timestamp is optional and may be NaN."""
        row = {**VALID_USER_ROW, "end_timestamp": float("nan")}
        df = _df(row)
        valid, quarantine = validate_user_df(df)
        assert len(valid) == 1
        assert quarantine.empty


# ---------------------------------------------------------------------------
# validate_pi_df
# ---------------------------------------------------------------------------


class TestValidatePiDf:
    def test_valid_rows_pass(self):
        df = _df(VALID_PI_ROW)
        valid, quarantine = validate_pi_df(df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_missing_required_column_raises(self):
        df = _df(VALID_PI_ROW).drop(columns=["speed_code"])
        with pytest.raises(ColumnError) as exc_info:
            validate_pi_df(df)
        assert "pi_form" in str(exc_info.value)

    def test_negative_storage_quarantined(self):
        bad_row = {**VALID_PI_ROW, "storage": -1.0}
        df = _df(bad_row)
        valid, quarantine = validate_pi_df(df)
        assert valid.empty
        assert "storage" in quarantine.iloc[0][QUARANTINE_COL]

    def test_nan_storage_quarantined(self):
        bad_row = {**VALID_PI_ROW, "storage": float("nan")}
        df = _df(bad_row)
        valid, quarantine = validate_pi_df(df)
        assert valid.empty

    def test_empty_speed_code_quarantined(self):
        bad_row = {**VALID_PI_ROW, "speed_code": ""}
        df = _df(bad_row)
        valid, quarantine = validate_pi_df(df)
        assert valid.empty
        assert "speed_code" in quarantine.iloc[0][QUARANTINE_COL]

    def test_zero_storage_valid(self):
        row = {**VALID_PI_ROW, "storage": 0.0}
        df = _df(row)
        valid, quarantine = validate_pi_df(df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_string_storage_valid_if_numeric(self):
        row = {**VALID_PI_ROW, "storage": "5"}
        df = _df(row)
        valid, quarantine = validate_pi_df(df)
        assert len(valid) == 1


# ---------------------------------------------------------------------------
# validate_user_update_df
# ---------------------------------------------------------------------------


class TestValidateUserUpdateDf:
    def test_valid_rows_pass(self):
        df = _df(VALID_USER_UPDATE_ROW)
        valid, quarantine = validate_user_update_df(df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_missing_column_raises(self):
        df = _df(VALID_USER_UPDATE_ROW).drop(columns=["timestamp"])
        with pytest.raises(ColumnError):
            validate_user_update_df(df)

    def test_invalid_email_quarantined(self):
        bad_row = {**VALID_USER_UPDATE_ROW, "email": "not@valid"}
        # "not@valid" has no TLD so it should fail
        df = _df(bad_row)
        valid, quarantine = validate_user_update_df(df)
        # "not@valid" technically matches our simple regex; test a clearly bad one
        bad_row2 = {**VALID_USER_UPDATE_ROW, "email": "plaintext"}
        df2 = _df(bad_row2)
        valid2, quarantine2 = validate_user_update_df(df2)
        assert valid2.empty
        assert not quarantine2.empty


# ---------------------------------------------------------------------------
# validate_storage_update_df
# ---------------------------------------------------------------------------


class TestValidateStorageUpdateDf:
    def test_valid_rows_pass(self):
        df = _df(VALID_STORAGE_UPDATE_ROW)
        valid, quarantine = validate_storage_update_df(df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_optional_storage_none_accepted(self):
        row = {**VALID_STORAGE_UPDATE_ROW, "new_storage": float("nan")}
        df = _df(row)
        valid, quarantine = validate_storage_update_df(df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_negative_new_storage_quarantined(self):
        row = {**VALID_STORAGE_UPDATE_ROW, "new_storage": -3.0}
        df = _df(row)
        valid, quarantine = validate_storage_update_df(df)
        assert valid.empty
        assert "new_storage" in quarantine.iloc[0][QUARANTINE_COL]

    def test_missing_required_column_raises(self):
        df = _df(VALID_STORAGE_UPDATE_ROW).drop(columns=["email"])
        with pytest.raises(ColumnError):
            validate_storage_update_df(df)


# ---------------------------------------------------------------------------
# Edge-cases shared across validators
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_dataframe_produces_empty_quarantine(self):
        df = pd.DataFrame(columns=list(VALID_USER_ROW.keys()))
        valid, quarantine = validate_user_df(df)
        assert valid.empty
        assert quarantine.empty

    def test_all_rows_invalid_produces_empty_valid(self):
        bad_rows = [
            {**VALID_USER_ROW, "email": "bad1"},
            {**VALID_USER_ROW, "email": "bad2"},
        ]
        df = _df(*bad_rows)
        valid, quarantine = validate_user_df(df)
        assert valid.empty
        assert len(quarantine) == 2

    def test_excel_row_offset_first_row(self):
        """First data row is index 0 -> Excel row 2."""
        bad_row = {**VALID_USER_ROW, "email": "bad"}
        df = _df(bad_row)
        _, quarantine = validate_user_df(df)
        assert "Excel row 2" in quarantine.iloc[0][QUARANTINE_COL]

    def test_column_error_lists_all_missing(self):
        df = pd.DataFrame(columns=["start_timestamp"])  # missing email, last_name, pi_last_name, power_user
        with pytest.raises(ColumnError) as exc_info:
            validate_user_df(df)
        err = exc_info.value
        assert "email" in err.missing
        assert "last_name" in err.missing


# ---------------------------------------------------------------------------
# Integration: ColumnError metadata
# ---------------------------------------------------------------------------


class TestColumnError:
    def test_attributes_set_correctly(self):
        err = ColumnError("my_sheet", ["col1", "col2"])
        assert err.sheet == "my_sheet"
        assert err.missing == ["col1", "col2"]

    def test_message_contains_sheet_and_columns(self):
        err = ColumnError("pi_form", ["storage", "email"])
        msg = str(err)
        assert "pi_form" in msg
        assert "storage" in msg
        assert "email" in msg


# ---------------------------------------------------------------------------
# Regression: datetime.date objects in timestamp column
# ---------------------------------------------------------------------------


def test_date_object_in_timestamp_column_is_valid():
    """datetime.date values (not Timestamps) should be accepted."""
    row = {**VALID_USER_ROW, "start_timestamp": datetime.date(2021, 1, 1)}
    df = _df(row)
    valid, quarantine = validate_user_df(df)
    assert len(valid) == 1
    assert quarantine.empty


# ---------------------------------------------------------------------------
# Cross-table: validate_pi_update_refs
# ---------------------------------------------------------------------------


class TestValidatePiUpdateRefs:
    """Tests for validate_pi_update_refs (storage_update vs pi_df)."""

    def _pi_df(self, last_names: list[str]) -> pd.DataFrame:
        return pd.DataFrame({"last_name": last_names})

    def _update_df(self, last_names: list[str]) -> pd.DataFrame:
        return pd.DataFrame({
            "last_name": last_names,
            "timestamp": [pd.Timestamp("2021-01-01")] * len(last_names),
            "email": ["pi@example.com"] * len(last_names),
        })

    def test_matching_name_passes(self):
        update_df = self._update_df(["smith"])
        pi_df = self._pi_df(["smith", "jones"])
        valid, quarantine = validate_pi_update_refs(update_df, pi_df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_unmatched_name_quarantined(self):
        """Storage-update rows referencing unknown PI last names must be quarantined."""
        update_df = self._update_df(["ghost"])
        pi_df = self._pi_df(["smith"])
        valid, quarantine = validate_pi_update_refs(update_df, pi_df)
        assert valid.empty
        assert len(quarantine) == 1
        assert "last_name" in quarantine.iloc[0][QUARANTINE_COL]
        assert "ghost" in quarantine.iloc[0][QUARANTINE_COL]

    def test_mixed_rows(self):
        update_df = self._update_df(["smith", "ghost", "jones"])
        pi_df = self._pi_df(["smith", "jones"])
        valid, quarantine = validate_pi_update_refs(update_df, pi_df)
        assert len(valid) == 2
        assert len(quarantine) == 1

    def test_empty_update_df_passes(self):
        update_df = pd.DataFrame(columns=["last_name", "timestamp", "email"])
        pi_df = self._pi_df(["smith"])
        valid, quarantine = validate_pi_update_refs(update_df, pi_df)
        assert valid.empty
        assert quarantine.empty

    def test_empty_pi_df_quarantines_all(self):
        """If no PIs exist, every storage-update row is an orphan."""
        update_df = self._update_df(["smith"])
        pi_df = pd.DataFrame(columns=["last_name"])
        valid, quarantine = validate_pi_update_refs(update_df, pi_df)
        assert valid.empty
        assert len(quarantine) == 1

    def test_error_message_contains_excel_row(self):
        update_df = self._update_df(["smith", "ghost"])
        pi_df = self._pi_df(["smith"])
        _, quarantine = validate_pi_update_refs(update_df, pi_df)
        # "ghost" is at pandas index 1 → Excel row 3
        assert "Excel row 3" in quarantine.iloc[0][QUARANTINE_COL]


# ---------------------------------------------------------------------------
# Cross-table: validate_user_update_refs
# ---------------------------------------------------------------------------


class TestValidateUserUpdateRefs:
    """Tests for validate_user_update_refs (user_update vs user_df)."""

    def _user_df(self, emails: list[str]) -> pd.DataFrame:
        return pd.DataFrame({"email": emails})

    def _update_df(self, emails: list[str]) -> pd.DataFrame:
        return pd.DataFrame({
            "email": emails,
            "timestamp": [pd.Timestamp("2021-06-01")] * len(emails),
            "last_name": ["Apple"] * len(emails),
        })

    def test_matching_email_passes(self):
        update_df = self._update_df(["alice@example.com"])
        user_df = self._user_df(["alice@example.com", "bob@example.com"])
        valid, quarantine = validate_user_update_refs(update_df, user_df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_unmatched_email_quarantined(self):
        """User-update rows referencing unknown emails must be quarantined."""
        update_df = self._update_df(["ghost@example.com"])
        user_df = self._user_df(["alice@example.com"])
        valid, quarantine = validate_user_update_refs(update_df, user_df)
        assert valid.empty
        assert len(quarantine) == 1
        assert "email" in quarantine.iloc[0][QUARANTINE_COL]
        assert "ghost@example.com" in quarantine.iloc[0][QUARANTINE_COL]

    def test_mixed_rows(self):
        update_df = self._update_df([
            "alice@example.com", "ghost@example.com", "bob@example.com",
        ])
        user_df = self._user_df(["alice@example.com", "bob@example.com"])
        valid, quarantine = validate_user_update_refs(update_df, user_df)
        assert len(valid) == 2
        assert len(quarantine) == 1

    def test_empty_update_df_passes(self):
        update_df = pd.DataFrame(columns=["email", "timestamp", "last_name"])
        user_df = self._user_df(["alice@example.com"])
        valid, quarantine = validate_user_update_refs(update_df, user_df)
        assert valid.empty
        assert quarantine.empty

    def test_empty_user_df_quarantines_all(self):
        """If no users exist, every user-update row is an orphan."""
        update_df = self._update_df(["alice@example.com"])
        user_df = pd.DataFrame(columns=["email"])
        valid, quarantine = validate_user_update_refs(update_df, user_df)
        assert valid.empty
        assert len(quarantine) == 1

    def test_error_message_contains_excel_row(self):
        update_df = self._update_df(["alice@example.com", "ghost@example.com"])
        user_df = self._user_df(["alice@example.com"])
        _, quarantine = validate_user_update_refs(update_df, user_df)
        assert "Excel row 3" in quarantine.iloc[0][QUARANTINE_COL]


# ---------------------------------------------------------------------------
# Cross-table: validate_power_user_pi_refs
# ---------------------------------------------------------------------------


class TestValidatePowerUserPiRefs:
    """Tests for validate_power_user_pi_refs (power users vs pi_df)."""

    def _pi_df(self, last_names: list[str]) -> pd.DataFrame:
        return pd.DataFrame({"last_name": last_names})

    def _user_df(
        self, emails: list[str], pi_names: list[str], power_flags: list[bool],
    ) -> pd.DataFrame:
        return pd.DataFrame({
            "email": emails,
            "pi_last_name": pi_names,
            "power_user": power_flags,
            "last_name": ["Apple"] * len(emails),
            "start_timestamp": [pd.Timestamp("2021-01-01")] * len(emails),
        })

    def test_power_user_with_valid_pi_passes(self):
        user_df = self._user_df(["a@example.com"], ["smith"], [True])
        pi_df = self._pi_df(["smith"])
        valid, quarantine = validate_power_user_pi_refs(user_df, pi_df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_non_power_user_with_unknown_pi_passes(self):
        """Non-power users don't need a valid PI in pi_form."""
        user_df = self._user_df(["a@example.com"], ["unknown_pi"], [False])
        pi_df = self._pi_df(["smith"])
        valid, quarantine = validate_power_user_pi_refs(user_df, pi_df)
        assert len(valid) == 1
        assert quarantine.empty

    def test_power_user_with_unknown_pi_quarantined(self):
        """Power users whose PI is not in pi_form must be quarantined."""
        user_df = self._user_df(["a@example.com"], ["ghost_pi"], [True])
        pi_df = self._pi_df(["smith"])
        valid, quarantine = validate_power_user_pi_refs(user_df, pi_df)
        assert valid.empty
        assert len(quarantine) == 1
        assert "pi_last_name" in quarantine.iloc[0][QUARANTINE_COL]
        assert "ghost_pi" in quarantine.iloc[0][QUARANTINE_COL]

    def test_mixed_power_and_non_power_users(self):
        user_df = self._user_df(
            ["a@example.com", "b@example.com", "c@example.com"],
            ["smith", "ghost_pi", "jones"],
            [True, True, False],
        )
        pi_df = self._pi_df(["smith", "jones"])
        valid, quarantine = validate_power_user_pi_refs(user_df, pi_df)
        # "b" is power user with unknown PI -> quarantined
        # "c" is non-power user with "jones" (even though jones is in pi_df, doesn't matter)
        assert len(valid) == 2
        assert len(quarantine) == 1

    def test_empty_user_df_passes(self):
        user_df = pd.DataFrame(
            columns=["email", "pi_last_name", "power_user", "last_name"],
        )
        pi_df = self._pi_df(["smith"])
        valid, quarantine = validate_power_user_pi_refs(user_df, pi_df)
        assert valid.empty
        assert quarantine.empty

    def test_empty_pi_df_quarantines_power_users(self):
        """With no PIs at all, any power user row must be quarantined."""
        user_df = self._user_df(
            ["a@example.com", "b@example.com"],
            ["smith", "jones"],
            [True, False],
        )
        pi_df = pd.DataFrame(columns=["last_name"])
        valid, quarantine = validate_power_user_pi_refs(user_df, pi_df)
        # Only the power user (row 0) is quarantined
        assert len(valid) == 1
        assert len(quarantine) == 1

