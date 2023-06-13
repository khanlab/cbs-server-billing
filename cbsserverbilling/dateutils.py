"""Utilities for handling datetimes."""

import calendar
import datetime


def get_days_in_range(
    start_date: datetime.date, end_date: datetime.date,
) -> list[datetime.date]:
    """Return an (inclusive) list of days between the given dates."""
    return [
        start_date + datetime.timedelta(days=delta)
        for delta in range((end_date - start_date).days + 1)
    ]


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
