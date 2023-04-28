"""Billing policy definitions."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from jinja2 import Environment

from cbsserverbilling.dateutils import get_days_in_range, get_end_of_period
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
        end_cutoff = get_end_of_period(
            start_date.year,
            start_date.month,
            self.MIN_BILL_USAGE,
        )
        start_cutoff = get_end_of_period(
            start_date.year,
            start_date.month,
            self.PERIOD_LENGTH - self.MIN_BILL_USAGE,
        )
        min_days = max((end_cutoff - start_date).days, (end_date - start_cutoff).days)
        power_users = record.enumerate_power_users(start_date, end_date)

        price_record = []
        first_price_applied = False
        period_days = get_days_in_range(start_date, end_date)
        for user in power_users:
            active_days = {date for date in period_days if user.is_active(date)}
            power_user_days = {date for date in active_days if user.is_power_user(date)}
            charge = len(power_user_days) >= min_days
            if not charge:
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
                    if (not user.end_date)
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
