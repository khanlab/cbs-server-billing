"""Tests for cbsserverbilling.billing"""

import datetime

from cbsserverbilling import billing

MOCK_PI_FORM = "tests/resources/mock_pi_form.xlsx"
MOCK_STORAGE_UPDATE_FORM = "tests/resources/mock_storage_update_form.xlsx"
MOCK_USER_FORM = "tests/resources/mock_user_form.xlsx"
MOCK_USER_UPDATE_FORM = "tests/resources/mock_user_update_form.xlsx"


def test_load_pi_df():
    """Test that `load_pi_df` properly loads the PI form data."""
    pi_df = billing.load_pi_df(MOCK_PI_FORM)
    for actual, expected in zip(
        pi_df.columns,
        [
            "start_timestamp",
            "email",
            "first_name",
            "last_name",
            "storage",
            "pi_is_power_user",
            "speed_code",
        ],
    ):
        assert actual == expected
    assert len(pi_df.index) == 10


def test_load_user_df():
    """Test that `load_user_df` properly loads the user form data."""
    user_df = billing.load_user_df(MOCK_USER_FORM)
    for actual, expected in zip(
        user_df.columns,
        [
            "start_timestamp",
            "email",
            "first_name",
            "last_name",
            "pi_last_name",
            "end_timestamp",
            "power_user",
        ],
    ):
        assert actual == expected
    assert len(user_df.index) == 14


def test_preprocess_forms():
    """Test that `preprocess_forms` correctly assembles the data"""
    pi_df, user_df = billing.preprocess_forms(MOCK_PI_FORM, MOCK_USER_FORM)
    assert len(pi_df.index) == 10
    assert len(user_df.index) == 24
    assert user_df.loc[14, "last_name"] == "Apple"


def test_is_billable_pi():
    """Test is_billable_pi"""
    pi_df, _ = billing.preprocess_forms(MOCK_PI_FORM, MOCK_USER_FORM)
    storage_update_df = billing.load_storage_update_df(
        MOCK_STORAGE_UPDATE_FORM
    )
    storage_record = billing.StorageRecord(pi_df, storage_update_df)
    quarter_start = datetime.date(2020, 11, 1)
    policy = billing.BillingPolicy()

    # Not closed
    assert policy.is_billable_pi(storage_record, "Apple", quarter_start)
    # Closed before cutoff
    assert not policy.is_billable_pi(
        storage_record, "Watermelon", quarter_start
    )
    # Closed after cutoff
    assert policy.is_billable_pi(storage_record, "Jackfruit", quarter_start)


def test_speed_code():
    """Test that the correct speed code is returned."""
    pi_df, _ = billing.preprocess_forms(MOCK_PI_FORM, MOCK_USER_FORM)
    storage_update_df = billing.load_storage_update_df(
        MOCK_STORAGE_UPDATE_FORM
    )
    storage_record = billing.StorageRecord(pi_df, storage_update_df)
    date = datetime.date(2021, 1, 31)

    assert storage_record.get_speed_code("Durian", date) == "DDDD"
    assert storage_record.get_speed_code("Banana", date) == "BBBC"


def test_enumerate_all_users():
    """Test that the correct speed code is returned."""
    _, user_df = billing.preprocess_forms(MOCK_PI_FORM, MOCK_USER_FORM)
    user_update_df = billing.load_user_update_df(MOCK_USER_UPDATE_FORM)
    power_users_record = billing.PowerUsersRecord(user_df, user_update_df)
    date = datetime.date(2021, 1, 31)

    users = power_users_record.enumerate_all_users(
        datetime.date(2020, 12, 16), date
    )
    assert {user[0] for user in users} == {
        "Elderberry",
        "Fruit",
        "Grape",
        "Honeydew",
        "Lemon",
        "Nectarine",
        "Orange",
        "Pomegranate",
        "Quince",
        "Strawberry",
        "Tomato",
        "Vanilla",
        "Xigua",
        "Apple",
        "Banana",
        "Cherry",
        "Durian",
        "Ice Cream",
        "Jackfruit",
        "Kiwi",
        "Mango",
        "Raspberry",
        "Watermelon",
    }


def test_billing_policy():
    """Test that `BillingPolicy` works properly for all PIs."""
    pi_df, user_df = billing.preprocess_forms(MOCK_PI_FORM, MOCK_USER_FORM)
    storage_update_df = billing.load_storage_update_df(
        MOCK_STORAGE_UPDATE_FORM
    )
    user_update_df = billing.load_user_update_df(MOCK_USER_UPDATE_FORM)
    storage_record = billing.StorageRecord(pi_df, storage_update_df)
    power_users_record = billing.PowerUsersRecord(user_df, user_update_df)
    policy = billing.BillingPolicy()

    quarter_start = datetime.date(2020, 11, 1)

    # Check that users active < 2 months aren't charged
    expected_user_prices = {
        "Mango": 1000 / 4,
        "Nectarine": 500 / 4,
        "Orange": 0,
        "Pomegranate": 500 / 4,
        "Quince": 0,
        "Xigua": 500 / 4,
    }
    for last_name, _, _, price in policy.enumerate_quarterly_power_user_prices(
        power_users_record, "Mango", quarter_start
    ):
        assert price == expected_user_prices[last_name]

    # Check that mid-quarter storage updates are applied (or not) correctly
    assert (
        policy.get_quarterly_storage_price(
            storage_record, "Durian", quarter_start
        )
        == 1 * 50 / 4
    )
    assert (
        policy.get_quarterly_storage_price(
            storage_record, "Banana", quarter_start
        )
        == 15 * 50 / 4
    )

    for pi_last_name, expected_total in zip(
        [
            "Apple",
            "Banana",
            "Cherry",
            "Durian",
            "Ice Cream",
            "Jackfruit",
            "Kiwi",
            "Mango",
            "Raspberry",
        ],
        [
            250,
            (15 * 50 / 4) + 250,
            62.5 + 250,
            12.5 + 375,
            25,
            37.5 + 250,
            50 + 375,
            125 + 625,
            50 + 375,
        ],
    ):

        assert (
            policy.get_quarterly_total_price(
                storage_record, power_users_record, pi_last_name, quarter_start
            )
            == expected_total
        )


def test_generate_pi_bill(capsys, tmp_path):
    """Test that `generate_pi_bill` populates a bill correctly."""
    with open(
        "tests/resources/kiwi_expected.tex", "r", encoding="utf-8"
    ) as expected_file:
        expected_bill = expected_file.read()

    # Check account cancelled before quarter cutoff
    billing.generate_pi_bill(
        [
            MOCK_PI_FORM,
            MOCK_STORAGE_UPDATE_FORM,
            MOCK_USER_FORM,
            MOCK_USER_UPDATE_FORM,
        ],
        "Watermelon",
        "2020-11-01",
    )
    bill = capsys.readouterr().out
    assert bill == ""

    billing.generate_pi_bill(
        [
            MOCK_PI_FORM,
            MOCK_STORAGE_UPDATE_FORM,
            MOCK_USER_FORM,
            MOCK_USER_UPDATE_FORM,
        ],
        "Kiwi",
        "2020-11-01",
    )

    bill = capsys.readouterr().out
    for actual_line, expected_line in zip(
        bill.split("\n\n"), expected_bill.split("\n\n")
    ):
        # Date line will always change
        if expected_line.startswith(r"{\bf Date"):
            continue
        assert actual_line == expected_line

    billing.generate_pi_bill(
        [
            MOCK_PI_FORM,
            MOCK_STORAGE_UPDATE_FORM,
            MOCK_USER_FORM,
            MOCK_USER_UPDATE_FORM,
        ],
        "Kiwi",
        "2020-11-01",
        out_file=tmp_path / "test.txt",
    )

    with open(tmp_path / "test.txt", "r", encoding="utf-8") as report_file:
        bill = report_file.read()
    for actual_line, expected_line in zip(
        bill.split("\n\n"), expected_bill.split("\n\n")
    ):
        if expected_line.startswith(r"{\bf Date"):
            continue
        assert actual_line == expected_line
