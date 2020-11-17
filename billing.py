"""Utilities to calculate CBS Server billing"""

import pandas as pd

# Storage price in dollars/TB/year
STORAGE_PRICE = 50

# Power user prices in dollars/year
FIRST_POWERUSER_PRICE = 1000
ADDITIONAL_POWERUSER_PRICE = 500

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
                "poweruser"})
    user_df = user_df.assign(poweruser=user_df["poweruser"] == "Yes")
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
                "pi_is_poweruser",
            "Speed code": "speed_code",
            "Required storage needs (in TB)": "storage"})
    pi_df = pi_df.assign(pi_is_poweruser=pi_df["pi_is_poweruser"] == "Yes")
    return pi_df

def add_pis_to_user_df(pi_df, user_df):
    """Add PI user accounts to the user dataframe."""
    pi_user_df = pi_df.loc[:, ["timestamp", "email", "first_name", "last_name", "pi_is_poweruser"]]
    pi_user_df = pi_user_df.assign(pi_last_name=pi_user_df["last_name"])
    pi_user_df = pi_user_df.rename(
        columns={
            "pi_is_poweruser": "poweruser"})
    return pd.concat([user_df, pi_user_df], ignore_index=True)

def assemble_report(pi_df, user_df, pi_lastname, quarter_end):
    """Calculate and report price for a PIs CBS server usage."""
    pi_row = pi_df.loc[pi_df["last_name"] == pi_lastname, :]
    pi_timestamp = pi_row["timestamp"].iloc[0]
    pi_speed_code = pi_row["speed_code"].iloc[0]
    if pi_timestamp > quarter_end:
        print("No PI storage this quarter.")
        return
    pi_storage = pi_row["storage"].iloc[0]
    storage_subtotal = pi_storage * STORAGE_PRICE * 0.25
    pi_row = pi_row.assign(
        fixed=STORAGE_PRICE,
        quarterly=0.25)
    pi_row = pi_row.assign(
        price=pi_row["storage"] * pi_row["fixed"] * pi_row["quarterly"])

    print(pi_row.loc[:,
        ["timestamp", "storage", "fixed", "quarterly", "price"]])
    print("Storage: Speed Code: {}, Subtotal: ${:.2f}".format(
        pi_speed_code,
        storage_subtotal))

    pi_users = user_df.loc[user_df["pi_last_name"] == pi_lastname, :]
    pi_users = pi_users.loc[pi_users["timestamp"] < quarter_end, :]
    pi_powerusers = pi_users.loc[pi_users["poweruser"], :]
    pi_powerusers.index = range(len(pi_powerusers))
    pi_powerusers = pi_powerusers.assign(
        fixed=pi_powerusers.index.map(user_price_by_index),
        quarterly=0.25)
    pi_powerusers = pi_powerusers.assign(
        price=pi_powerusers["fixed"] * pi_powerusers["quarterly"])
    poweruser_subtotal = sum(pi_powerusers.loc[:, "price"])

    print(pi_powerusers.loc[:,
        ["last_name", "timestamp", "fixed", "quarterly", "price"]])
    print("Power users: Speed Code: {}, Subtotal: ${:.2f}".format(
        pi_speed_code,
        poweruser_subtotal))

    total = storage_subtotal + poweruser_subtotal

    print("Total: ${:.2f}".format(total))

def user_price_by_index(index):
    """Calculate price for a user based on their (zero-)index."""
    if index <= 0:
        return FIRST_POWERUSER_PRICE
    return ADDITIONAL_POWERUSER_PRICE
