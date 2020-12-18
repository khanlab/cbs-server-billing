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

env = Environment(loader=PackageLoader("cbsserverbilling", "templates"))


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

    return datetime.date(year, month, calendar.monthrange(year, month)[-1])


def is_billable_pi(storage_record, pi_last_name, start_date):
    """Check whether a PI is billable in this quarter.

    A PI is billable if their account was created before the end of the
    period, and either still open or closed more than two months into the
    period.

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
    bool
        True if the PI is billable in the specified period.
    """
    end_date = get_end_of_period(start_date.year, start_date.month, 3)
    if storage_record.get_storage_start(pi_last_name) > end_date:
        return False
    cutoff_date = get_end_of_period(start_date.year, start_date.month, 2)
    account_close_date = storage_record.get_pi_account_close_date(pi_last_name)
    if pd.isna(account_close_date) or (account_close_date > cutoff_date):
        return True
    return False


class BillingPolicy:
    """Class containing all billing policy information."""

    STORAGE_PRICE = 50
    FIRST_POWER_USER_PRICE = 1000
    ADDITIONAL_POWER_USER_PRICE = 500

    def get_quarterly_storage_price(
        self, storage_record, pi_last_name, start_date
    ):
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
        cutoff_date = get_end_of_period(start_date.year, start_date.month, 1)
        if storage_record.get_storage_start(pi_last_name) > cutoff_date:
            return 0
        return (
            min(
                storage_record.get_storage_amount(pi_last_name, cutoff_date),
                storage_record.get_storage_amount(
                    pi_last_name,
                    get_end_of_period(start_date.year, start_date.month, 2),
                ),
            )
            * self.STORAGE_PRICE
            * 0.25
        )

    def enumerate_quarterly_power_user_prices(
        self, power_users_record, pi_last_name, start_date
    ):
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
        end_date = get_end_of_period(start_date.year, start_date.month, 3)
        power_users = power_users_record.enumerate_power_users(
            pi_last_name, start_date, end_date
        )

        price_record = []
        first_price_applied = False
        for name, user_start, user_end in power_users:
            if (not pd.isna(user_end)) and user_end <= get_end_of_period(
                start_date.year, start_date.month, 2
            ):
                price = 0
            elif user_start > get_end_of_period(
                start_date.year, start_date.month, 1
            ):
                price = 0
            elif not first_price_applied:
                price = self.FIRST_POWER_USER_PRICE * 0.25
                first_price_applied = True
            else:
                price = self.ADDITIONAL_POWER_USER_PRICE * 0.25
            price_record.append((name, user_start, user_end, price))

        return price_record

    def get_quarterly_power_user_price(
        self, power_users_record, pi_last_name, quarter_start
    ):
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

        return sum(
            [
                user[3]
                for user in self.enumerate_quarterly_power_user_prices(
                    power_users_record, pi_last_name, quarter_start
                )
            ]
        )

    def get_quarterly_total_price(
        self, storage_record, power_users_record, pi_last_name, quarter_start
    ):
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
        return self.get_quarterly_storage_price(
            storage_record, pi_last_name, quarter_start
        ) + self.get_quarterly_power_user_price(
            power_users_record, pi_last_name, quarter_start
        )

    def generate_quarterly_bill_tex(
        self, storage_record, power_users_record, pi_last_name, quarter_start
    ):
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
        end_date = get_end_of_period(
            quarter_start.year, quarter_start.month, 3
        )
        dates = {
            "start": quarter_start.strftime("%b %d, %Y"),
            "end": end_date.strftime("%b %d, %Y"),
            "bill": datetime.date.today().strftime("%b %d, %Y"),
        }
        storage = {
            "timestamp": (
                storage_record.get_storage_start(pi_last_name).strftime(
                    "%b %d, %Y"
                )
            ),
            "amount": storage_record.get_storage_amount(
                pi_last_name, end_date
            ),
            "price": "{:.2f}".format(STORAGE_PRICE),
            "subtotal": "{:.2f}".format(
                self.get_quarterly_storage_price(
                    storage_record, pi_last_name, quarter_start
                )
            ),
        }
        power_users = [
            {
                "last_name": record[0],
                "start_date": record[1].strftime("%b %d, %Y"),
                "end_date": (
                    "N/A"
                    if pd.isna(record[2])
                    else record[2].strftime("%b %d, %Y")
                ),
                "price": "{:.2f}".format(record[3] * 4),
                "subtotal": "{:.2f}".format(record[3]),
            }
            for record in self.enumerate_quarterly_power_user_prices(
                power_users_record, pi_last_name, quarter_start
            )
        ]
        power_users_subtotal = "{:.2f}".format(
            self.get_quarterly_power_user_price(
                power_users_record, pi_last_name, quarter_start
            )
        )
        total = "{:.2f}".format(
            self.get_quarterly_total_price(
                storage_record, power_users_record, pi_last_name, quarter_start
            )
        )
        speed_code = storage_record.get_speed_code(pi_last_name)

        template = env.get_template(BILL_TEMPLATE)
        return template.render(
            pi_name=pi_name,
            pi_last_name=pi_last_name,
            dates=dates,
            storage=storage,
            power_users=power_users,
            power_users_subtotal=power_users_subtotal,
            total=total,
            speed_code=speed_code,
        )


class StorageRecord:
    """Record describing all PIs' storage use.

    Attributes
    ----------
    storage_df : DataFrame
        Dataframe containing storage information.
    storage_update_df : DataFrame
        Datafram containing updates to PIs' requested storage.
    """

    def __init__(self, storage_df, storage_update_df):
        self.storage_df = storage_df
        self.storage_update_df = storage_update_df

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
        return (
            self.storage_df.loc[
                self.storage_df["last_name"] == pi_last_name, "first_name"
            ].iloc[0]
            + " "
            + pi_last_name
        )

    def get_storage_start(self, pi_last_name):
        """Get a PI's storage start date.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.

        Returns
        -------
        date
            Date this PI's storage started.
        """
        return (
            self.storage_df.loc[
                self.storage_df["last_name"] == pi_last_name, "start_timestamp"
            ]
            .iloc[0]
            .date()
        )

    def get_pi_account_close_date(self, pi_last_name):
        """Get a PI's account closure date, if any.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.

        Returns
        -------
        date or None
            Date this PI's account was closed, if any.
        """
        closure_row = self.storage_update_df.loc[
                (self.storage_update_df["last_name"] == pi_last_name)
                & (self.storage_update_df["account_closed"]),
                "timestamp",
            ]
        if len(closure_row) == 0:
            return None
        return closure_row.iloc[0].date()

    def get_storage_amount(self, pi_last_name, date):
        """Get the amount of storage allocated to this PI on a given date.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.
        date : date
            Date to check storage price.

        Returns
        -------
        float
            Amount of storage (in TB) allocated to this PI.
        """
        pi_storage_updates = self.storage_update_df.loc[
            (self.storage_update_df["last_name"] == pi_last_name)
            & (self.storage_update_df["timestamp"].dt.date <= date),
            :,
        ]
        if len(pi_storage_updates) > 0:
            return pi_storage_updates.loc[
                pi_storage_updates["timestamp"].idxmax(), "new_storage"
            ]
        pi_storage = self.storage_df.loc[
            (self.storage_df["last_name"] == pi_last_name)
            & (self.storage_df["start_timestamp"].dt.date <= date),
            :,
        ]
        if len(pi_storage) > 0:
            return pi_storage.loc[:, "storage"].iloc[0]
        return 0

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
            self.storage_df["last_name"] == pi_last_name, "speed_code"
        ].iloc[0]


class PowerUsersRecord:
    """Record describing the users described by the forms.

    Attributes
    ----------
    power_user_df : DataFrame
        Dataframe containing each user during the quarter. Should be generated
        by this module to apply the expected structure.
    power_user_update_df : DataFrame
        Dataframe containing updates to user accounts defined in the power
        user dataframe.
    """

    def __init__(self, power_user_df, power_user_update_df):
        self.power_user_df = power_user_df
        self.power_user_update_df = power_user_update_df

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
            ["last_name", "start_timestamp"],
        ]
        out_df = out_df.loc[
            out_df["start_timestamp"].dt.date <= end_date, "last_name"
        ]
        out_list = []
        for name in out_df:
            is_power_user, user_start, user_end = self.describe_user(
                name, start_date, end_date
            )
            if not is_power_user:
                continue
            out_list.append((name, user_start, user_end))

        return sorted(out_list, key=lambda x: x[1])

    def describe_user(self, last_name, period_start, period_end):
        """Check whether a user was a power user in a given period.

        Parameters
        ----------
        last_name : str
            The user's last name.
        period_start : date
            First day of the period to check.
        period_end : date
            Last day of the period to check.

        Returns
        -------
        (bool, date or None, date or None)
            Whether the user was a power user during the power, then if so, the
            start and end dates of that user's active period.
        """
        orig_row = self.power_user_df.loc[
            self.power_user_df["last_name"] == last_name, :
        ]
        orig_dates = [
            orig_row.loc[:, "start_timestamp"].iloc[0],
            orig_row.loc[:, "end_timestamp"].iloc[0],
        ]
        orig_power_user = orig_row.loc[:, "power_user"].iloc[0]
        relevant_updates = self.power_user_update_df.loc[
            (self.power_user_update_df["last_name"] == last_name)
            & (self.power_user_update_df["timestamp"].dt.date <= period_end)
            & (
                (self.power_user_update_df["new_end_timestamp"].notna())
                | (self.power_user_update_df["new_power_user"].notna())
            ),
            ["timestamp", "new_end_timestamp", "new_power_user"],
        ]
        if len(relevant_updates) == 0:
            if (
                orig_power_user
                and (pd.isna(orig_dates[1]) or (orig_dates[1] >= period_start))
                and (orig_dates[0] < period_end)
            ):
                return True, orig_dates[0], orig_dates[1]
            return False, None, None

        status_updates = relevant_updates.loc[
            relevant_updates["new_power_user"].notna(),
            ["timestamp", "new_power_user"],
        ]
        end_date_updates = relevant_updates.loc[
            relevant_updates["new_end_timestamp"].notna(),
            ["timestamp", "new_end_timestamp"],
        ]
        if len(end_date_updates) > 0:
            newest_end_date = end_date_updates.loc[
                end_date_updates["timestamp"].idxmax(), "new_end_timestamp"
            ]
        if len(status_updates) > 0:
            currently_power_user = status_updates.loc[
                status_updates["timestamp"].idxmax(), "new_power_user"
            ]
            status_update_date = status_updates.loc[
                status_updates["timestamp"].idxmax(), "timestamp"
            ].date()

        if len(status_updates) == 0:
            if (
                orig_power_user
                and (newest_end_date >= period_start)
                and (orig_dates[0] < period_end)
            ):
                return True, orig_dates[0], newest_end_date
            return False, None, None

        # Status has changed
        end_date = (
            newest_end_date if len(end_date_updates) > 0 else orig_dates[1]
        )
        if currently_power_user:
            start_date = status_update_date
        else:
            start_date = orig_dates[0]
            end_date = min(end_date, status_update_date)
        if (start_date < period_end) and (
            pd.isna(end_date) or (end_date > period_start)
        ):
            return True, start_date, end_date
        return False, None, None


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
            "PI Last Name": "pi_last_name",
            "Contract end date (account expiration)": "end_timestamp",
            (
                "Do you need your account to be a power user account?"
            ): "power_user",
        }
    )
    user_df = user_df.assign(
        power_user=user_df["power_user"].str.strip() == "Yes"
    )
    return user_df


def load_user_update_df(user_update_form_path):
    """Load dataframe containing updates to user dataframe.

    Parameters
    ----------
    user_update_form_path : str
        Path to the user update form.

    Returns
    -------
    DataFrame
        Dataframe containing updates to user account specifications.
    """
    user_update_df = pd.read_excel(user_update_form_path)
    user_update_df = user_update_df.rename(
        columns={
            "Timestamp": "timestamp",
            "Email Address": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "PI Last Name": "pi_last_name",
            (
                "Request access to additional datashare "
                + "(specify PI's last name)"
            ): "additional_datashare",
            (
                "Update contract end date (account expiration)"
            ): "new_end_timestamp",
            "Change account type": "new_power_user",
            "List projects for which you need security access": "new_projects",
            (
                "By clicking yes below, you agree with these general terms."
            ): "agree",
            "Optional: Please feel free to leave any feedback.": "feedback",
        }
    )
    user_update_df = user_update_df.assign(
        agree=user_update_df["agree"].str.strip() == "Yes",
        new_power_user=user_update_df["new_power_user"].map(
            lambda x: None if pd.isna(x) else x.strip() == "Power user"
        ),
    )
    return user_update_df


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
            (
                "Would you like your account to be a power user account? "
                + "(There is a fee associated with power user accounts.)"
            ): "pi_is_power_user",
            "Speed code": "speed_code",
            "Required storage needs (in TB)": "storage",
        }
    )
    pi_df = pi_df.assign(
        pi_is_power_user=pi_df["pi_is_power_user"].str.strip() == "Yes"
    )
    return pi_df


def load_storage_update_df(storage_update_form_path):
    """Load dataframe containing updates to PI dataframe.

    Parameters
    ----------
    storage_update_form_path : str
        Path to the storage update form.

    Returns
    -------
    DataFrame
        Dataframe containing updates to PI storage needs.
    """
    storage_update_df = pd.read_excel(storage_update_form_path)
    storage_update_df = storage_update_df.rename(
        columns={
            "Timestamp": "timestamp",
            "Email Address": "email",
            "First name": "first_name",
            "Last name": "last_name",
            "Required storage needs (in TB)": "new_storage",
            "Speed code": "speed_code",
            (
                "Do you need separate access groups for specific projects?  "
                + "If yes, please list the project names."
            ): "access_groups",
            (
                "By clicking yes below, you agree with these general terms."
            ): "agree",
            "Optional: Please feel free to leave any feedback.": "feedback",
            "I would like to close my server account": "account_closed",
        }
    )
    storage_update_df = storage_update_df.assign(
        agree=storage_update_df["agree"].str.strip() == "Yes",
        account_closed=storage_update_df["account_closed"].str.strip()
        == "Yes",
    )
    return storage_update_df


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
            "pi_is_power_user",
        ],
    ]
    pi_user_df = pi_user_df.assign(
        pi_last_name=pi_user_df["last_name"], end_timestamp=(None)
    )
    pi_user_df = pi_user_df.rename(columns={"pi_is_power_user": "power_user"})
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


def generate_all_pi_bills(paths, quarter_start_iso, out_dir):
    """Loop through all PIs and save a bill for each.

    Parameters
    ----------
    paths : list of str
        Path to the PI form data, storage update form data, user form data,
        and user update form data, in that order.
    quarter_start_iso : str
        ISO formatted end date of the billing quarter.
    out_dir : str, optional
        Directory into which to output bill text files.
    """
    [pi_path, storage_update_path, user_path, user_update_path] = paths
    pi_df, _ = preprocess_forms(pi_path, user_path)

    for pi_last_name in pi_df.loc[:, "last_name"]:
        out_file = os.path.join(
            out_dir,
            "pi-{}_quarter-{}_bill.tex".format(
                pi_last_name, quarter_start_iso
            ),
        )
        generate_pi_bill(
            [pi_path, storage_update_path, user_path, user_update_path],
            pi_last_name,
            quarter_start_iso,
            out_file,
        )


def generate_pi_bill(paths, pi_last_name, quarter, out_file=None):
    """Open data files and produce a report for one PI.

    If the PI is not billable this quarter, this will do nothing.

    Parameters
    ----------
    paths: list of str
        Paths to PI form data, storage update form data, user form data,
        and user update form data, in that order.
    pi_last_name : str
        Last name of the PI to bill.
    quarter : str
        ISO formatted start date of the billing quarter.
    out_file : str, optional
        Path to output text file.
    """
    pi_df, user_df = preprocess_forms(paths[0], paths[2])
    storage_update_df = load_storage_update_df(paths[1])
    user_update_df = load_user_update_df(paths[3])

    quarter_start = datetime.date.fromisoformat(quarter)

    storage_record = StorageRecord(pi_df, storage_update_df)
    power_users_record = PowerUsersRecord(user_df, user_update_df)

    if not is_billable_pi(storage_record, pi_last_name, quarter_start):
        return

    policy = BillingPolicy()

    bill_tex = policy.generate_quarterly_bill_tex(
        storage_record, power_users_record, pi_last_name, quarter_start
    )
    if out_file is not None:
        with open(out_file, "w") as writable:
            writable.write(bill_tex)
        return

    print(bill_tex, end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process CBS Server billing data."
    )
    parser.add_argument("pi_form", type=str, help="path to the PI form data")
    parser.add_argument(
        "storage_update_form",
        type=str,
        help="path to the storage update form data",
    )
    parser.add_argument(
        "user_form", type=str, help="path to the user form data"
    )
    parser.add_argument(
        "user_update_form", type=str, help="path to the user update form data"
    )
    parser.add_argument(
        "quarter_start", type=str, help="first day of the quarter to bill"
    )
    parser.add_argument(
        "out_dir", type=str, help="directory into which to output bill files"
    )

    args = parser.parse_args()
    generate_all_pi_bills(
        [
            args.pi_form,
            args.storage_update_form,
            args.user_form,
            args.user_update_form,
        ],
        args.quarter_start,
        args.out_dir,
    )
