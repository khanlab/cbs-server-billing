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
    billing.generate_pi_bill(MOCK_PI_FORM,
                             MOCK_USER_FORM,
                             "Apple",
                             ["2020-10-01", "2020-12-31"])

    bill = capsys.readouterr().out
    expected_bill = "\n".join([
        "Billing report for Apple",
        "Storage",
        "Start: 2019-12-10, Size: 20 TB, Annual price per TB: $50.00, "
        + "Quarterly Price: $250.00",
        "Speed code: AAAA, Subtotal: $250.00",
        "Power Users",
        "Speed code: AAAA, Subtotal: $0.00",
        "Total: $250.00\n"])

    assert bill == expected_bill

    billing.generate_pi_bill(MOCK_PI_FORM,
                             MOCK_USER_FORM,
                             "Banana",
                             ["2020-10-01", "2020-12-31"],
                             out_file=tmp_path / "test.txt")

    expected_bill = "\n".join([
        "Billing report for Banana",
        "Storage",
        "Start: 2019-12-10, Size: 10 TB, Annual price per TB: $50.00, "
        + "Quarterly Price: $125.00",
        "Speed code: BBBB, Subtotal: $125.00",
        "Power Users",
        "Name: Fruit, Start: 2020-01-27, Annual price: $1000.00, "
        + "Quarterly price: $250.00",
        "Speed code: BBBB, Subtotal: $250.00",
        "Total: $375.00\n"])

    with open(tmp_path / "test.txt", "r") as report_file:
        assert report_file.read() == expected_bill
