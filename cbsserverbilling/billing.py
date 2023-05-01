"""Utilities to calculate CBS Server billing."""
from __future__ import annotations

import datetime
import os
from collections.abc import Iterable
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from jinja2 import Environment, PackageLoader

from cbsserverbilling.policy import BillingPolicy, get_end_of_period
from cbsserverbilling.records import BillableProjectRecord

TIME_ZONE = ZoneInfo("America/Toronto")

env = Environment(
    loader=PackageLoader("cbsserverbilling", "templates"),
    autoescape=True,
)


def summarize_all_pi_bills(
    all_records: Iterable[BillableProjectRecord],
    quarter_start: datetime.date,
    out_file: os.PathLike,
) -> None:
    """Print a summary of all PI bills."""
    policy = BillingPolicy()
    quarter_end = get_end_of_period(
        quarter_start.year,
        quarter_start.month,
        policy.PERIOD_LENGTH,
    )
    records = [
        record for record in all_records if policy.is_billable_pi(record, quarter_start)
    ]

    pd.DataFrame(
        {
            "pi": [record.get_pi_last_name() for record in records],
            "storage_amount": [
                policy.get_quarterly_storage_amount(record, quarter_start)
                for record in records
            ],
            "storage_price": [
                policy.get_quarterly_storage_price(record, quarter_start)
                for record in records
            ],
            "billed_power_users": [
                len(
                    [
                        user
                        for user, price in policy.enumerate_quarterly_power_user_prices(
                            record,
                            quarter_start,
                        )
                        if price > 0
                    ],
                )
                for record in records
            ],
            "compute_price": [
                policy.get_quarterly_power_user_price(record, quarter_start)
                for record in records
            ],
            "total_price": [
                policy.get_quarterly_total_price(record, quarter_start)
                for record in records
            ],
            "speed_code": [record.get_speed_code(quarter_end) for record in records],
        },
    ).sort_values(by="pi").to_excel(out_file, index=False, engine="openpyxl")

    total_storage = sum(
        policy.get_quarterly_storage_price(record, quarter_start) for record in records
    )
    total_compute = sum(
        policy.get_quarterly_power_user_price(record, quarter_start)
        for record in records
    )
    total = total_storage + total_compute

    print(f"Total (Storage): {total_storage}")
    print(f"Mean (Storage): {total_storage / len(records)}")
    print(f"Total (Compute): {total_compute}")
    print(f"Mean (Compute): {total_compute / len(records)}")
    print(f"Total (Overall): {total}")
    print(f"Mean (Overall): {total / len(records)}")


def generate_all_pi_bills(
    all_records: Iterable[BillableProjectRecord],
    quarter_start: datetime.date,
    out_dir: os.PathLike[str] | str,
) -> None:
    """Loop through all PIs and save a bill for each."""
    policy = BillingPolicy()
    records = [
        record for record in all_records if policy.is_billable_pi(record, quarter_start)
    ]

    for record in records:
        out_file = Path(out_dir) / (
            f"pi-{record.get_pi_last_name()}"
            f"_started-{record.get_storage_start().isoformat()}"
            f"_quarter-{quarter_start.isoformat()}"
            "_bill.tex"
        )
        generate_pi_bill(
            record,
            quarter_start,
            out_file,
        )


def generate_pi_bill(
    record: BillableProjectRecord,
    quarter_start: datetime.date,
    out_file: os.PathLike | None = None,
) -> None:
    """Open data files and produce a report for one PI.

    If the PI is not billable this quarter, this will do nothing.
    """
    policy = BillingPolicy()

    if not policy.is_billable_pi(record, quarter_start):
        return

    if record.get_pi_last_name() == "Butler":
        print(record.get_storage_amount(quarter_start))

    bill_tex = policy.generate_quarterly_bill_tex(
        record,
        quarter_start,
        env,
    )
    if out_file is not None:
        with Path(out_file).open("w", encoding="utf-8") as writable:
            writable.write(bill_tex)
