"""Utilities to calculate CBS Server billing"""

import pandas as pd

# Storage price in dollars/TB/year
STORAGE_PRICE = 50

# Power user prices in dollars/year
FIRST_POWERUSER_PRICE = 1000
ADDITIONAL_POWERUSER_PRICE = 500

class QuarterlyStorageRecord:
    def __init__(self, pi_storage_df, quarter_end):
        self.pi_storage_df = pi_storage_df
        self.quarter_end = quarter_end

    def get_storage_start(self):
        return self.pi_storage_df["timestamp"].iloc[0]

    def get_storage_amount(self):
        return self.pi_storage_df["storage"].iloc[0]

    def get_speed_code(self):
        return self.pi_storage_df["speed_code"].iloc[0]

    def calculate_storage_price(self):
        pi_storage = self.get_storage_amount()
        return pi_storage * STORAGE_PRICE * 0.25

class QuarterlyPowerUsersRecord:
    def __init__(self, pi_power_user_df, quarter_end):
        self.pi_power_user_df = pi_power_user_df
        self.quarter_end = quarter_end

    def calculate_power_users_price(self):
        power_user_subtotal = sum(self.pi_power_user_df.loc[:, "price"])
        return power_user_subtotal

    def enumerate_power_users(self):
        return list(self.pi_power_user_df.loc[:,
            ["timestamp", "last_name", "price"]].itertuples(index=False))

class QuarterlyBill:
    def __init__(
            self,
            pi_last_name,
            quarterly_storage,
            quarterly_power_users,
            quarter_end):
        self.pi_last_name = pi_last_name
        self.quarterly_storage = quarterly_storage
        self.quarterly_power_users = quarterly_power_users
        self.quarter_end = quarter_end

    def calculate_total(self):
        return (
            self.quarterly_storage.calculate_storage_price()
            + self.quarterly_power_users.calculate_power_users_price())

    def print_bill(self):
        print("Billing report for {}".format(self.pi_last_name))
        print("Storage")
        print(
            ("Start: {}, Size: {} TB, Annual price per TB: ${:.2f}, "
                + "Quarterly Price: ${:.2f}").format(
                self.quarterly_storage.get_storage_start().date(),
                self.quarterly_storage.get_storage_amount(),
                STORAGE_PRICE,
                self.quarterly_storage.calculate_storage_price()))
        print("Speed code: {}, Subtotal: ${:.2f}".format(
            self.quarterly_storage.get_speed_code(),
            self.quarterly_storage.calculate_storage_price()))
        print("Power Users")
        for start, last_name, price in (
                self.quarterly_power_users.enumerate_power_users()):
            print(
                    ("Name: {}, Start: {}, "
                        + "Quarterly price: ${:.2f}").format(
                    last_name,
                    start.date(),
                    price))
        print("Speed code: {}, Subtotal: ${:.2f}".format(
            self.quarterly_storage.get_speed_code(),
            self.quarterly_power_users.calculate_power_users_price()))
        print("Total: ${:.2f}".format(self.calculate_total()))

def load_user_df(user_form_path):
    """Load user Google Forms data into a usable pandas dataframe."""
    user_df = pd.read_excel(user_form_path)
    user_df = user_df.rename(
        columns={
            "Timestamp": "timestamp",
            "Email Address": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "PI Name": "pi_last_name",
            "Do you need your account to be a power user account? "
            + "(There is a fee associated with power user accounts.  "
            + "Check with your PI first!)":
                "power_user"})
    user_df = user_df.assign(power_user=user_df["power_user"] == "Yes")
    return user_df

def load_pi_df(pi_form_path):
    """Load PI Google Forms data into a usable pandas dataframe."""
    pi_df = pd.read_excel(pi_form_path)
    pi_df = pi_df.rename(
        columns={
            "Timestamp": "timestamp",
            "Email Address": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "Would you like your account to be a power user account? "
            + "(There is a fee associated with power user accounts.)":
                "pi_is_power_user",
            "Speed code": "speed_code",
            "Required storage needs (in TB)": "storage"})
    pi_df = pi_df.assign(pi_is_power_user=pi_df["pi_is_power_user"] == "Yes")
    return pi_df

def add_pis_to_user_df(pi_df, user_df):
    """Add PI user accounts to the user dataframe."""
    pi_user_df = pi_df.loc[:, ["timestamp", "email", "first_name", "last_name", "pi_is_power_user"]]
    pi_user_df = pi_user_df.assign(pi_last_name=pi_user_df["last_name"])
    pi_user_df = pi_user_df.rename(
        columns={
            "pi_is_power_user": "power_user"})
    return pd.concat([user_df, pi_user_df], ignore_index=True)

def assemble_report(pi_df, user_df, pi_lastname, quarter_end):
    """Calculate and report price for a PIs CBS server usage."""
    pi_row = pi_df.loc[pi_df["last_name"] == pi_lastname, :]
    pi_timestamp = pi_row["timestamp"].iloc[0]
    if pi_timestamp > quarter_end:
        print("No PI storage this quarter.")
        return None
    pi_row = pi_row.assign(
        fixed=STORAGE_PRICE,
        quarterly=0.25)
    pi_row = pi_row.assign(
        price=pi_row["storage"] * pi_row["fixed"] * pi_row["quarterly"])
    storage_record = QuarterlyStorageRecord(pi_row, quarter_end)

    pi_users = user_df.loc[user_df["pi_last_name"] == pi_lastname, :]
    pi_users = pi_users.loc[pi_users["timestamp"] < quarter_end, :]
    pi_power_users = pi_users.loc[pi_users["power_user"], :]
    pi_power_users.index = range(len(pi_power_users))
    pi_power_users = pi_power_users.assign(
        fixed=pi_power_users.index.map(user_price_by_index),
        quarterly=0.25)
    pi_power_users = pi_power_users.assign(
        price=pi_power_users["fixed"] * pi_power_users["quarterly"])
    power_user_record = QuarterlyPowerUsersRecord(
        pi_power_users,
        quarter_end)

    return QuarterlyBill(
        pi_lastname,
        storage_record,
        power_user_record,
        quarter_end)

def user_price_by_index(index):
    """Calculate price for a user based on their (zero-)index."""
    if index <= 0:
        return FIRST_POWERUSER_PRICE
    return ADDITIONAL_POWERUSER_PRICE
