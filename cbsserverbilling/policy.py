from __future__ import annotations

import calendar
import datetime

from jinja2 import Environment
import pandas as pd

from cbsserverbilling.spreadsheet import StorageRecord, PowerUsersRecord

# Storage price in dollars/TB/year
STORAGE_PRICE = 50

# Power user prices in dollars/year
FIRST_POWERUSER_PRICE = 1000
ADDITIONAL_POWERUSER_PRICE = 500

BILL_TEMPLATE = "cbs_server_bill.tex.jinja"


class BillingPolicy:
    """Class containing all billing policy information."""

    STORAGE_PRICE = 50
    FIRST_POWER_USER_PRICE = 1000
    ADDITIONAL_POWER_USER_PRICE = 500

    PERIOD_LENGTH = 3
    MIN_BILL_USAGE = 2

    def is_billable_pi(
        self,
        storage_record: StorageRecord,
        pi_last_name: str,
        start_date: datetime.date,
    ) -> bool:
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
        end_date = get_end_of_period(
            start_date.year, start_date.month, self.PERIOD_LENGTH
        )
        if storage_record.get_storage_start(pi_last_name) > end_date:
            return False
        cutoff_date = get_end_of_period(
            start_date.year,
            start_date.month,
            self.MIN_BILL_USAGE,
        )
        account_close_date = storage_record.get_pi_account_close_date(pi_last_name)
        if pd.isna(account_close_date) or (account_close_date > cutoff_date):
            return True
        return False

    def get_quarterly_storage_amount(
        self,
        storage_record: StorageRecord,
        pi_last_name: str,
        start_date: datetime.date,
    ) -> float:
        """Calculate a quarter's storage usage for one PI.

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
            Total storage used by the PI in this quarter
        """
        cutoff_date = get_end_of_period(
            start_date.year,
            start_date.month,
            self.PERIOD_LENGTH - self.MIN_BILL_USAGE,
        )
        if storage_record.get_storage_start(pi_last_name) > cutoff_date:
            return 0
        return min(
            storage_record.get_storage_amount(pi_last_name, cutoff_date),
            storage_record.get_storage_amount(
                pi_last_name,
                get_end_of_period(
                    start_date.year, start_date.month, self.MIN_BILL_USAGE
                ),
            ),
        )

    def get_quarterly_storage_price(
        self,
        storage_record: StorageRecord,
        pi_last_name: str,
        start_date: datetime.date,
    ) -> float:
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
        return (
            self.get_quarterly_storage_amount(storage_record, pi_last_name, start_date)
            * self.STORAGE_PRICE
            * 0.25
        )

    def enumerate_quarterly_power_user_prices(
        self,
        power_users_record: PowerUsersRecord,
        pi_last_name: str,
        start_date: datetime.date,
    ) -> list[tuple[str, datetime.date, datetime.date, float]]:
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
        end_date = get_end_of_period(
            start_date.year, start_date.month, self.PERIOD_LENGTH
        )
        power_users = power_users_record.enumerate_power_users(
            pi_last_name, start_date, end_date
        )

        price_record = []
        first_price_applied = False
        for name, user_start, user_end in power_users:
            if (pd.notna(user_end)) and user_end.date() <= get_end_of_period(
                start_date.year, start_date.month, self.MIN_BILL_USAGE
            ):
                price = 0
            elif user_start.date() > get_end_of_period(
                start_date.year,
                start_date.month,
                self.PERIOD_LENGTH - self.MIN_BILL_USAGE,
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
        self,
        power_users_record: PowerUsersRecord,
        pi_last_name: str,
        quarter_start: datetime.date,
    ) -> float:
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
            user[3]
            for user in self.enumerate_quarterly_power_user_prices(
                power_users_record, pi_last_name, quarter_start
            )
        )

    def get_quarterly_total_price(
        self,
        storage_record: StorageRecord,
        power_users_record: PowerUsersRecord,
        pi_last_name: str,
        quarter_start: datetime.date,
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
        self,
        storage_record: StorageRecord,
        power_users_record: PowerUsersRecord,
        pi_last_name: str,
        quarter_start: datetime.date,
        env: Environment,
    ) -> str:
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
            quarter_start.year, quarter_start.month, self.PERIOD_LENGTH
        )
        dates = {
            "start": quarter_start.strftime("%b %d, %Y"),
            "end": end_date.strftime("%b %d, %Y"),
            "bill": datetime.date.today().strftime("%b %d, %Y"),
        }
        subtotal = self.get_quarterly_storage_price(
            storage_record, pi_last_name, quarter_start
        )
        storage = {
            "timestamp": (
                storage_record.get_storage_start(pi_last_name).strftime("%b %d, %Y")
            ),
            "amount": storage_record.get_storage_amount(pi_last_name, end_date),
            "price": f"{STORAGE_PRICE:.2f}",
            "subtotal": f"{subtotal:.2f}",
        }
        power_users = [
            {
                "last_name": record[0],
                "start_date": record[1].strftime("%b %d, %Y"),
                "end_date": (
                    "N/A" if pd.isna(record[2]) else record[2].strftime("%b %d, %Y")
                ),
                "price": f"{record[3] * 4:.2f}",
                "subtotal": f"{record[3]:.2f}",
            }
            for record in self.enumerate_quarterly_power_user_prices(
                power_users_record, pi_last_name, quarter_start
            )
        ]
        power_users_subtotal = self.get_quarterly_power_user_price(
            power_users_record, pi_last_name, quarter_start
        )
        total = self.get_quarterly_total_price(
            storage_record, power_users_record, pi_last_name, quarter_start
        )
        total = f"{total:.2f}"
        speed_code = storage_record.get_speed_code(pi_last_name, datetime.date.today())

        template = env.get_template(BILL_TEMPLATE)
        return template.render(
            pi_name=pi_name,
            pi_last_name=pi_last_name,
            dates=dates,
            storage=storage,
            power_users=power_users,
            power_users_subtotal=f"{power_users_subtotal:.2f}",
            total=total,
            speed_code=speed_code,
        )


def get_end_of_period(start_year: int, start_month: int, num_months: int):
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
