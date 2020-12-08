"""Tests for cbsserverbilling.billing"""

import datetime

from cbsserverbilling import billing

MOCK_PI_FORM = "tests/resources/mock_pi_form.xlsx"
MOCK_USER_FORM = "tests/resources/mock_user_form.xlsx"


def test_load_pi_df():
    """Test that `load_pi_df` properly loads the PI form data."""
    pi_df = billing.load_pi_df(MOCK_PI_FORM)
    for actual, expected in zip(pi_df.columns, ["start_timestamp",
                                                "email",
                                                "first_name",
                                                "last_name",
                                                "storage",
                                                "pi_is_power_user",
                                                "speed_code"]):
        assert actual == expected
    assert len(pi_df.index) == 7


def test_load_user_df():
    """Test that `load_user_df` properly loads the user form data."""
    user_df = billing.load_user_df(MOCK_USER_FORM)
    for actual, expected in zip(user_df.columns, ["start_timestamp",
                                                  "email",
                                                  "first_name",
                                                  "last_name",
                                                  "pi_last_name",
                                                  "end_timestamp",
                                                  "power_user"]):
        assert actual == expected
    assert len(user_df.index) == 5


def test_preprocess_forms():
    """Test that `preprocess_forms` correctly assembles the data"""
    pi_df, user_df = billing.preprocess_forms(MOCK_PI_FORM, MOCK_USER_FORM)
    assert len(pi_df.index) == 7
    assert len(user_df.index) == 12
    assert user_df.loc[5, "last_name"] == "Apple"


def test_billing_policy():
    """Test that `BillingPolicy` works properly for all PIs."""
    pi_df, user_df = billing.preprocess_forms(MOCK_PI_FORM, MOCK_USER_FORM)
    storage_record = billing.StorageRecord(pi_df)
    power_users = user_df.loc[user_df["power_user"], :]
    power_users_record = billing.PowerUsersRecord(power_users)
    policy = billing.BillingPolicy()

    quarter_start = datetime.date(2020, 10, 1)

    for pi_last_name, expected_total in zip(
            [
                "Apple",
                "Banana",
                "Cherry",
                "Durian",
                "Ice Cream",
                "Jackfruit",
                "Kiwi"],
            [250, 125+250, 62.5+250, 12.5+375, 25, 37.5+250, 50+375]):

        assert (policy.get_quarterly_total_price(storage_record,
                                                 power_users_record,
                                                 pi_last_name,
                                                 quarter_start)
                == expected_total)


def test_generate_pi_bill(capsys, tmp_path):
    """Test that `generate_pi_bill` populates a bill correctly."""
    with open("tests/resources/kiwi_expected.tex", "r") as expected_file:
        expected_bill = expected_file.read()

    billing.generate_pi_bill(MOCK_PI_FORM,
                             MOCK_USER_FORM,
                             "Kiwi",
                             "2020-11-01")

    bill = capsys.readouterr().out
    for actual_line, expected_line in zip(
            bill.split("\n\n"),
            expected_bill.split("\n\n")):
        # Date line will always change
        if expected_line.startswith(r"{\bf Date"):
            continue
        assert actual_line == expected_line

    billing.generate_pi_bill(MOCK_PI_FORM,
                             MOCK_USER_FORM,
                             "Kiwi",
                             "2020-11-01",
                             out_file=tmp_path / "test.txt")

    with open(tmp_path / "test.txt", "r") as report_file:
        bill = report_file.read()
    for actual_line, expected_line in zip(
            bill.split("\n\n"),
            expected_bill.split("\n\n")):
        if expected_line.startswith(r"{\bf Date"):
            continue
        assert actual_line == expected_line
