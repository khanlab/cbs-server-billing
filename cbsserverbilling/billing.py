"""Utilities to calculate CBS Server billing"""

import argparse
import calendar
import datetime
import os

import pandas as pd
from jinja2 import Environment, PackageLoader

# Storage price in dollars/TB/year
STORAGE_PRICE = 50

# Power user prices in dollars/year
FIRST_POWERUSER_PRICE = 1000
ADDITIONAL_POWERUSER_PRICE = 500

BILL_TEMPLATE = "cbs_server_bill.tex.jinja"

env = Environment(
    loader=PackageLoader("cbsserverbilling", "templates"))


def get_end_of_period(start_year, start_month, num_months):
    """Return the end date of a period starting in a given month.

    Parameters
    ----------
    start_year : int
        Starting year of the period.
    start_month : int
        Starting month of the period.
    num_months : int
        Length in months of the period.

    Returns
    -------
    date
        Last day of the period.
    """
    year = start_year
    if num_months > 11:
        year += num_months // 12
        num_months = num_months % 12

    if num_months == 0 and start_month == 1:
        year -= 1
        month = 12
    elif start_month <= (13 - num_months):
        year = start_year
        month = start_month + (num_months - 1)
    else:
        year = start_year + 1
        month = start_month - (13 - num_months)

    return datetime.date(year,
                         month,
                         calendar.monthrange(year, month)[-1])


class BillingPolicy:
    """Class containing all billing policy information."""
    STORAGE_PRICE = 50
    FIRST_POWER_USER_PRICE = 1000
    ADDITIONAL_POWER_USER_PRICE = 500

    def get_quarterly_storage_price(self,
                                    storage_record,
                                    pi_last_name,
                                    start_date):
        """Calculate a quarter's storage price for one PI.

        Parameters
        ----------
        storage_record : StorageRecord
            Record with all the storage information.
        pi_last_name : str
            Last name of the PI to query.
        start_date : date
            Date in the first month of the quarter.

        Returns
        -------
        float
            Total storage price for the PI for the quarter.
        """
        end_date = get_end_of_period(start_date.year,
                                     start_date.month,
                                     3)
        if storage_record.get_storage_start(pi_last_name) > end_date:
            return 0
        storage_amount = storage_record.get_storage_amount(pi_last_name)
        return storage_amount * self.STORAGE_PRICE * 0.25

    def enumerate_quarterly_power_user_prices(self,
                                              power_users_record,
                                              pi_last_name,
                                              start_date):
        """Calculate the price each of one PI's power users in a quarter.

        Parameters
        ----------
        power_users_record : PowerUsersRecord
            Record with all the storage information.
        pi_last_name : str
            Last name of the PI to query.
        start_date : date
            Date in the first month of the quarter.

        Returns
        -------
        list of tuple
            A tuple for each of the PI's power users, including the user's
            name, start date, end date, and price.
        """
        end_date = get_end_of_period(start_date.year,
                                     start_date.month,
                                     3)
        power_users = power_users_record.enumerate_power_users(
            pi_last_name,
            start_date,
            end_date)

        price_record = []
        first_price_applied = False
        for name, user_start, user_end in power_users:
            if ((user_end is not None)
                and user_end <= get_end_of_period(start_date.year,
                                                 start_date.month,
                                                 2)):
                price = 0
            elif user_start > get_end_of_period(start_date.year,
                                                start_date.month,
                                                1):
                price = 0
            elif not first_price_applied:
                price = self.FIRST_POWER_USER_PRICE * 0.25
                first_price_applied = True
            else:
                price = self.ADDITIONAL_POWER_USER_PRICE * 0.25
            price_record.append((name, user_start, user_end, price))

        return price_record

    def get_quarterly_power_user_price(self,
                                       power_users_record,
                                       pi_last_name,
                                       quarter_start):
        """Calculate a quarter's power user price for one PI.

        Parameters
        ----------
        power_users_record : PowerUsersRecord
            Record with all the power user information.
        pi_last_name : str
            Last name of the PI to query.
        quarter_start : date
            Date in the first month of the quarter.

        Returns
        -------
        float
            Total power users price for the PI for the quarter.
        """

        return sum([
            user[3] for user in self.enumerate_quarterly_power_user_prices(
                power_users_record,
                pi_last_name,
                quarter_start)])

    def get_quarterly_total_price(self,
                                  storage_record,
                                  power_users_record,
                                  pi_last_name,
                                  quarter_start):
        """Calculate a quarter's total price for one PI.

        Parameters
        ----------
        power_users_record : PowerUsersRecord
            Record with all the power user information.
        storage_record : StorageRecord
            Record with all the storage information.
        pi_last_name : str
            Last name of the PI to query.
        quarter_start : date
            Date in the first month of the quarter.

        Returns
        -------
        float
            Total power users price for the PI for the quarter.
        """
        return (
            self.get_quarterly_storage_price(storage_record,
                                             pi_last_name,
                                             quarter_start)
            + self.get_quarterly_power_user_price(power_users_record,
                                                  pi_last_name,
                                                  quarter_start))

    def generate_quarterly_bill_tex(self,
                                    storage_record,
                                    power_users_record,
                                    pi_last_name,
                                    quarter_start):
        """Generate tex file of a quarterly bill.

        Parameters
        ----------
        power_users_record : PowerUsersRecord
            Record with all the power user information.
        storage_record : StorageRecord
            Record with all the storage information.
        pi_last_name : str
            Last name of the PI to query.
        quarter_start : date
            Date in the first month of the quarter.
        """
        pi_name = storage_record.get_pi_full_name(pi_last_name)
        start_date = quarter_start.strftime("%b %d, %Y")
        end_date = get_end_of_period(quarter_start.year,
                                     quarter_start.month,
                                     3).strftime(
            "%b %d, %Y")
        bill_date = datetime.date.today().strftime("%b %d, %Y")
        storage = {
            "timestamp": (storage_record
                          .get_storage_start(pi_last_name)
                          .strftime("%b %d, %Y")),
            "amount": storage_record.get_storage_amount(pi_last_name),
            "price": "{:.2f}".format(STORAGE_PRICE),
            "subtotal": "{:.2f}".format(
                self.get_quarterly_storage_price(storage_record,
                                                 pi_last_name,
                                                 quarter_start))}
        power_users = [
            {"last_name": record[0],
             "start_date": record[1].strftime("%b %d, %Y"),
             "end_date": "N/A" if record[2] is None
             else record[2].strftime("%b %d, %Y"),
             "price": "{:.2f}".format(record[3] * 4),
             "subtotal": "{:.2f}".format(record[3])}
            for record in self.enumerate_quarterly_power_user_prices(
                power_users_record,
                pi_last_name,
                quarter_start)]
        power_users_subtotal = "{:.2f}".format(
            self.get_quarterly_power_user_price(
                power_users_record,
                pi_last_name,
                quarter_start))
        total = "{:.2f}".format(self.get_quarterly_total_price(
            storage_record,
            power_users_record,
            pi_last_name,
            quarter_start))

        template = env.get_template(BILL_TEMPLATE)
        return template.render(pi_name=pi_name,
                               pi_last_name=pi_last_name,
                               start_date=start_date,
                               end_date=end_date,
                               bill_date=bill_date,
                               storage=storage,
                               power_users=power_users,
                               power_users_subtotal=power_users_subtotal,
                               total=total)


class StorageRecord:
    """Record describing all PIs' storage use.

    Attributes
    ----------
    storage_df : DataFrame
        Dataframe containing storage information.
    """

    def __init__(self, storage_df):
        self.storage_df = storage_df

    def get_pi_full_name(self, pi_last_name):
        """Get a PI's full name.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI

        Returns
        str
            Full name of the PI
        """
        return (self.storage_df.loc[
            self.storage_df["last_name"] == pi_last_name,
            "first_name"].iloc[0]
            + " "
            + pi_last_name)

    def get_storage_start(self, pi_last_name):
        """Get a PI's storage start date.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.

        Returns
        -------
        datetime
            Date this PI's storage started.
        """
        return self.storage_df.loc[
            self.storage_df["last_name"] == pi_last_name,
            "start_timestamp"].iloc[0]

    def get_storage_amount(self, pi_last_name):
        """Get the amount of storage allocated to this PI.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.

        Returns
        -------
        float
            Amount of storage (in TB) allocated to this PI.
        """
        return self.storage_df.loc[
            self.storage_df["last_name"] == pi_last_name,
            "storage"].iloc[0]

    def get_speed_code(self, pi_last_name):
        """Get the speed code associated with this PI.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.

        Returns
        -------
        str
            Speed code associated with this PI.
        """
        return self.storage_df.loc[
            self.storage_df["last_name"] == pi_last_name,
            "speed_code"].iloc[0]


class PowerUsersRecord:
    """Record describing the power users associated with one PI.

    Attributes
    ----------
    power_user_df : DataFrame
        Dataframe containing each power user associated with this PI during the
        quarter. Should be generated by this module to apply the expected
        structure.
    """
    def __init__(self, power_user_df):
        self.power_user_df = power_user_df

    def enumerate_power_users(self, pi_last_name, start_date, end_date):
        """Generate a list of power users associated with this PI.

        Parameters
        ----------
        pi_last_name : str
            PI of the users to enumerate.
        start_date : date
            First date to consider.
        end_date : date
            Last date to consider.

        Returns
        -------
        list of namedtuple
            A namedtuple for each user who was active on any day in the given
            range, where each namedtuple contains the user's last name, start
            date, and end date, in that order.
        """
        out_df = self.power_user_df.loc[
            self.power_user_df["pi_last_name"] == pi_last_name,
            ["last_name", "start_timestamp", "end_timestamp"]]
        out_df = out_df.loc[
            out_df["start_timestamp"] <= end_date, :]
        out_df = out_df.loc[
                (out_df["end_timestamp"] >= start_date)
                | out_df["end_timestamp"].isna(),
                :]
        return sorted(list(out_df.itertuples(index=False)),
                      key=lambda x: x[1])

    def power_user_is_active(self, last_name, date):
        """Check if a poweruser is active on a given date.

        Parameters
        ----------
        last_name : str
            Last name of the power user to check.
        date : date
            Date to check.
        """
        timestamps = self.power_user_df.loc[
            self.power_user_df["last_name"] == last_name,
            ["start_timestamp", "end_timestamp"]]
        start_timestamp = timestamps.iloc[0, 0]
        end_timestamp = timestamps.iloc[0, 1]

        return start_timestamp <= date <= end_timestamp


def load_user_df(user_form_path):
    """Load user Google Forms data into a usable pandas dataframe.

    Parameters
    ----------
    user_form_path : str
        Path to the excel sheet containing collected CBS server user data.

    Returns
    -------
    DataFrame
        A data frame with column names adjusted to be more usable, and the
        power user column cast to a boolean instead of a string.
    """
    user_df = pd.read_excel(user_form_path)
    user_df = user_df.rename(
        columns={
            "Timestamp": "start_timestamp",
            "Email Address": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "PI Name": "pi_last_name",
            "Contract end date (account expiration)": "end_timestamp",
            "Do you need your account to be a power user account? "
            + "(There is a fee associated with power user accounts.  "
            + "Check with your PI first!)":
                "power_user"})
    user_df = user_df.assign(power_user=user_df["power_user"] == "Yes",
                             start_timestamp=user_df["start_timestamp"].map(
                                 lambda dt: dt.date()),
                             end_timestamp=user_df["end_timestamp"].map(
                                 lambda dt: dt.date()))
    return user_df


def load_pi_df(pi_form_path):
    """Load PI Google Forms data into a usable pandas dataframe.

    Parameters
    ----------
    DataFrame
        A dataframe with column names adjusted to be more usable, and the PI
        power user column cast to a boolean instead of a string.
    """
    pi_df = pd.read_excel(pi_form_path)
    pi_df = pi_df.rename(
        columns={
            "Timestamp": "start_timestamp",
            "Email Address": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "Would you like your account to be a power user account? "
            + "(There is a fee associated with power user accounts.)":
                "pi_is_power_user",
            "Speed code": "speed_code",
            "Required storage needs (in TB)": "storage"})
    pi_df = pi_df.assign(pi_is_power_user=pi_df["pi_is_power_user"] == "Yes",
                         start_timestamp=pi_df["start_timestamp"].map(
                             lambda dt: dt.date()))
    return pi_df


def add_pis_to_user_df(pi_df, user_df):
    """Add PI user accounts to the user dataframe.

    PI user account information is stored in the PI Google Forms data by
    default, but is easier to work with if it's grouped with the other user
    account data.

    Parameters
    ----------
    pi_df : DataFrame
        Data frame including PI storage and PI account power user information.
    user_df : DataFrame
        Data frame including user account information.

    Returns
    -------
    DataFrame
        User dataframe with rows describing PI user accounts appended to the
        end.
    """
    pi_user_df = pi_df.loc[
        :,
        [
            "start_timestamp",
            "email",
            "first_name",
            "last_name",
            "pi_is_power_user"]]
    pi_user_df = pi_user_df.assign(
        pi_last_name=pi_user_df["last_name"],
        end_timestamp=(None))
    pi_user_df = pi_user_df.rename(
        columns={
            "pi_is_power_user": "power_user"})
    return pd.concat([user_df, pi_user_df], ignore_index=True)


def preprocess_forms(pi_path, user_path):
    """Load Google Forms data and rearrange it.

    Specifically, this loads both relevant sheets and adds PI accounts to the
    users table.

    Parameters
    ----------
    pi_path : str
        Path to the PI form data
    user_path : str
        Path to the user form data

    Returns
    -------
    tuple of DataFrame
        A tuple containing the resulting PI data frame then the user data
        frame.
    """
    pi_df = load_pi_df(pi_path)
    user_df = load_user_df(user_path)
    user_df = add_pis_to_user_df(pi_df, user_df)

    return (pi_df, user_df)


def generate_all_pi_bills(pi_path,
                          user_path,
                          quarter_start_iso,
                          out_dir):
    """Loop through all PIs and save a bill for each.

    Parameters
    ----------
    pi_path : str
        Path to the PI form data.
    user_path : str
        Path to the user form data.
    quarter_start_iso : str
        ISO formatted end date of the billing quarter.
    out_dir : str, optional
        Directory into which to output bill text files.
    """
    pi_df, _ = preprocess_forms(pi_path, user_path)

    for pi_last_name in pi_df.loc[:, "last_name"]:
        out_file = os.path.join(out_dir, "pi-{}_quarter-{}_bill.tex".format(
            pi_last_name,
            quarter_start_iso))
        generate_pi_bill(
            pi_path,
            user_path,
            pi_last_name,
            quarter_start_iso,
            out_file)


def generate_pi_bill(pi_path,
                     user_path,
                     pi_last_name,
                     quarter,
                     out_file=None):
    """Open data files and produce a report for one PI.

    Parameters
    ----------
    pi_path : str
        Path to the PI form data.
    user_path : str
        Path to the user form data.
    pi_last_name : str
        Last name of the PI to bill.
    quarter : str
        ISO formatted start date of the billing quarter.
    out_file : str, optional
        Path to output text file.
    """
    pi_df, user_df = preprocess_forms(pi_path, user_path)

    quarter_start = datetime.date.fromisoformat(quarter)

    storage_record = StorageRecord(pi_df)
    power_users = user_df.loc[user_df["power_user"], :]
    power_users_record = PowerUsersRecord(power_users)

    policy = BillingPolicy()

    bill_tex = policy.generate_quarterly_bill_tex(storage_record,
                                                  power_users_record,
                                                  pi_last_name,
                                                  quarter_start)
    if out_file is not None:
        with open(out_file, "w") as writable:
            writable.write(bill_tex)
        return

    print(bill_tex, end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process CBS Server billing data.")
    parser.add_argument("pi_form", type=str, help="path to the PI form data")
    parser.add_argument("user_form",
                        type=str,
                        help="path to the user form data")
    parser.add_argument("quarter_start",
                        type=str,
                        help="first day of the quarter to bill")
    parser.add_argument("out_dir",
                        type=str,
                        help="directory into which to output bill files")

    args = parser.parse_args()
    generate_all_pi_bills(
        args.pi_form,
        args.user_form,
        args.quarter_start,
        args.out_dir)
