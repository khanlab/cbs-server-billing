"""Billing policy definitions."""

from __future__ import annotations

import calendar
import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from jinja2 import Environment

from cbsserverbilling.records import BillableProjectRecord, User

# Storage price in dollars/TB/year
STORAGE_PRICE = 50

# Power user prices in dollars/year
FIRST_POWERUSER_PRICE = 1000
ADDITIONAL_POWERUSER_PRICE = 500

BILL_TEMPLATE = "cbs_server_bill.tex.jinja"

TIME_ZONE = ZoneInfo("America/Toronto")


class BillingPolicy:
    """Class containing all billing policy information."""

    STORAGE_PRICE = 50
    FIRST_POWER_USER_PRICE = 1000
    ADDITIONAL_POWER_USER_PRICE = 500

    PERIOD_LENGTH = 3
    MIN_BILL_USAGE = 2

    def is_billable_pi(
        self,
        record: BillableProjectRecord,
        start_date: datetime.date,
    ) -> bool:
        """Check whether a billable project is billable in this quarter.

        A billable project is billable if their account was created before the end of
        the period, and either still open or closed more than two months into the
        period.

        Parameters
        ----------
        record
            Record with all the storage information.
        start_date : date
            Date in the first month of the quarter.

        Returns
        -------
        bool
            True if the billable project is billable in the specified period.
        """
        end_date = get_end_of_period(
            start_date.year,
            start_date.month,
            self.PERIOD_LENGTH,
        )
        if record.get_storage_start() > end_date:
            return False
        cutoff_date = get_end_of_period(
            start_date.year,
            start_date.month,
            self.MIN_BILL_USAGE,
        )
        account_close_date = record.get_close_date()
        if (
            pd.isna(account_close_date)
            or (not account_close_date)
            or (account_close_date > cutoff_date)
        ):
            return True
        return False

    def get_quarterly_storage_amount(
        self,
        record: BillableProjectRecord,
        start_date: datetime.date,
    ) -> float:
        """Calculate a quarter's storage usage for one billable project.

        Parameters
        ----------
        record : BillableProjectRecord
            Record with all the storage information.
        start_date : date
            Date in the first month of the quarter.

        Returns
        -------
        float
            Total storage used by the billable project in this quarter
        """
        cutoff_date = get_end_of_period(
            start_date.year,
            start_date.month,
            self.PERIOD_LENGTH - self.MIN_BILL_USAGE,
        )
        if record.get_storage_start() > cutoff_date:
            return 0
        return min(
            record.get_storage_amount(cutoff_date),
            record.get_storage_amount(
                get_end_of_period(
                    start_date.year,
                    start_date.month,
                    self.MIN_BILL_USAGE,
                ),
            ),
        )

    def get_quarterly_storage_price(
        self,
        record: BillableProjectRecord,
        start_date: datetime.date,
    ) -> float:
        """Calculate a quarter's storage price for one billable project.

        Parameters
        ----------
        record
            Record with all the storage information.
        start_date
            Date in the first month of the quarter.

        Returns
        -------
        float
            Total storage price for the billable project for the quarter.
        """
        return (
            self.get_quarterly_storage_amount(record, start_date)
            * self.STORAGE_PRICE
            * 0.25
        )

    def enumerate_quarterly_power_user_prices(
        self,
        record: BillableProjectRecord,
        start_date: datetime.date,
    ) -> list[tuple[User, float]]:
        """Calculate the price each of one billable project's power users in a quarter.

        Parameters
        ----------
        record
            Record with all the storage information.
        start_date
            Date in the first month of the quarter.

        Returns
        -------
        list of tuple
            A tuple for each of the billable project's power users, including the user's
            name, start date, end date, and price.
        """
        end_date = get_end_of_period(
            start_date.year,
            start_date.month,
            self.PERIOD_LENGTH,
        )
        power_users = record.enumerate_power_users(start_date, end_date)

        price_record = []
        first_price_applied = False
        for user in power_users:
            if (
                pd.notna(user.end_date)
                and user.end_date
                <= get_end_of_period(
                    start_date.year,
                    start_date.month,
                    self.MIN_BILL_USAGE,
                )
            ) or (
                user.start_date
                > get_end_of_period(
                    start_date.year,
                    start_date.month,
                    self.PERIOD_LENGTH - self.MIN_BILL_USAGE,
                )
            ):
                price = 0.0
            elif not first_price_applied:
                price = self.FIRST_POWER_USER_PRICE * 0.25
                first_price_applied = True
            else:
                price = self.ADDITIONAL_POWER_USER_PRICE * 0.25
            price_record.append((user, price))

        return price_record

    def get_quarterly_power_user_price(
        self,
        record: BillableProjectRecord,
        quarter_start: datetime.date,
    ) -> float:
        """Calculate a quarter's power user price for one billable project.

        Parameters
        ----------
        record
            Record with all the power user information.
        quarter_start
            Date in the first month of the quarter.

        Returns
        -------
        float
            Total power users price for the billable project for the quarter.
        """
        return sum(
            price
            for _, price in self.enumerate_quarterly_power_user_prices(
                record,
                quarter_start,
            )
        )

    def get_quarterly_total_price(
        self,
        record: BillableProjectRecord,
        quarter_start: datetime.date,
    ) -> float:
        """Calculate a quarter's total price for one billable project.

        Parameters
        ----------
        record
            Record with all the storage information.
        quarter_start
            Date in the first month of the quarter.

        Returns
        -------
        float
            Total power users price for the billable project for the quarter.
        """
        return self.get_quarterly_storage_price(
            record,
            quarter_start,
        ) + self.get_quarterly_power_user_price(record, quarter_start)

    def generate_quarterly_bill_tex(
        self,
        record: BillableProjectRecord,
        quarter_start: datetime.date,
        env: Environment,
    ) -> str:
        """Generate tex file of a quarterly bill.

        Parameters
        ----------
        record
            Record with all the storage information.
        quarter_start
            Date in the first month of the quarter.
        env
            jinja2 environment
        """
        # pylint: disable=too-many-locals
        pi_name = record.get_pi_full_name()
        end_date = get_end_of_period(
            quarter_start.year,
            quarter_start.month,
            self.PERIOD_LENGTH,
        )
        dates = {
            "start": quarter_start.strftime("%b %d, %Y"),
            "end": end_date.strftime("%b %d, %Y"),
            "bill": datetime.datetime.now(tz=TIME_ZONE).strftime("%b %d, %Y"),
        }
        subtotal = self.get_quarterly_storage_price(record, quarter_start)
        storage = {
            "timestamp": (record.get_storage_start().strftime("%b %d, %Y")),
            "amount": record.get_storage_amount(end_date),
            "price": f"{STORAGE_PRICE:.2f}",
            "subtotal": f"{subtotal:.2f}",
        }
        power_users = [
            {
                "last_name": user.name,
                "start_date": user.start_date.strftime("%b %d, %Y"),
                "end_date": (
                    "N/A"
                    if ((not user.end_date) or pd.isna(user.end_date))
                    else user.end_date.strftime("%b %d, %Y")
                ),
                "price": f"{price * 4:.2f}",
                "subtotal": f"{price:.2f}",
            }
            for user, price in self.enumerate_quarterly_power_user_prices(
                record,
                quarter_start,
            )
        ]
        power_users_subtotal = self.get_quarterly_power_user_price(
            record,
            quarter_start,
        )
        total = self.get_quarterly_total_price(
            record,
            quarter_start,
        )
        total = f"{total:.2f}"
        speed_code = record.get_speed_code(datetime.datetime.now(tz=TIME_ZONE).date())

        template = env.get_template(BILL_TEMPLATE)
        return template.render(
            pi_name=pi_name,
            pi_last_name=pi_name,
            dates=dates,
            storage=storage,
            power_users=power_users,
            power_users_subtotal=f"{power_users_subtotal:.2f}",
            total=total,
            speed_code=speed_code,
        )


def get_end_of_period(
    start_year: int,
    start_month: int,
    num_months: int,
) -> datetime.date:
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
    months_in_year = 12
    year = start_year
    if num_months >= months_in_year:
        year += num_months // months_in_year
        num_months = num_months % months_in_year

    if (not num_months) and start_month == 1:
        year -= 1
        month = 12
    elif start_month <= (13 - num_months):
        year = start_year
        month = start_month + (num_months - 1)
    else:
        year = start_year + 1
        month = start_month - (13 - num_months)

    return datetime.date(year, month, calendar.monthrange(year, month)[-1])
