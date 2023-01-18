from __future__ import annotations

import datetime

import pandas as pd


class StorageRecord:
    """Record describing all PIs' storage use.

    Attributes
    ----------
    storage_df : DataFrame
        Dataframe containing storage information.
    storage_update_df : DataFrame
        Datafram containing updates to PIs' requested storage.
    """

    def __init__(
        self, storage_df: pd.DataFrame, storage_update_df: pd.DataFrame
    ) -> None:
        self.storage_df = storage_df
        self.storage_update_df = storage_update_df

    def get_pi_full_name(self, pi_last_name: str) -> str:
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

    def get_storage_start(self, pi_last_name: str) -> datetime.date:
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

    def get_pi_account_close_date(self, pi_last_name: str) -> datetime.date | None:
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

    def get_storage_amount(self, pi_last_name: str, date: datetime.date) -> float:
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
        total_storage = 0
        pi_storage = self.storage_df.loc[
            (self.storage_df["last_name"] == pi_last_name)
            & (self.storage_df["start_timestamp"].dt.date <= date),
            :,
        ]
        if len(pi_storage) > 0:
            total_storage += pi_storage.loc[:, "storage"].iloc[0]

        pi_storage_updates = self.storage_update_df.loc[
            (self.storage_update_df["last_name"] == pi_last_name)
            & (self.storage_update_df["timestamp"].dt.date <= date),
            :,
        ]
        if len(pi_storage_updates) > 0:
            total_storage += pi_storage_updates.loc[:, "new_storage"].sum()
        return total_storage

    def get_speed_code(self, pi_last_name: str, date: datetime.date) -> str:
        """Get the speed code associated with this PI on a date.

        Parameters
        ----------
        pi_last_name : str
            Last name of the PI.
        date: date
            Date on which to check the speed code.

        Returns
        -------
        str
            Speed code associated with this PI.
        """
        speed_code_updates = self.storage_update_df.loc[
            (self.storage_update_df["last_name"] == pi_last_name)
            & (pd.notna(self.storage_update_df["speed_code"]))
            & (self.storage_update_df["timestamp"].dt.date <= date),
            :,
        ]
        return (
            self.storage_df.loc[
                self.storage_df["last_name"] == pi_last_name, "speed_code"
            ].iloc[0]
            if len(speed_code_updates) == 0
            else speed_code_updates.loc[
                speed_code_updates["timestamp"].idxmax(), "speed_code"
            ]
        )


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

    def __init__(
        self, power_user_df: pd.DataFrame, power_user_update_df: pd.DataFrame
    ) -> None:
        self.power_user_df = power_user_df
        self.power_user_update_df = power_user_update_df

    def enumerate_all_users(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[tuple[str, datetime.date, datetime.date]]:
        """Generate a list of all users with an active account.

        Parameters
        ----------
        start_date : date
            First date to consider.
        end_date : date
            Last date to consider.

        Returns
        -------
        list of tuple
            A tuple for each user who was active on any day in the given
            range. The tuple contains the user's name, start date, and end
            date.
        """
        user_df = self.power_user_df.loc[
            self.power_user_df["start_timestamp"].dt.date < end_date,
            ["last_name", "start_timestamp", "end_timestamp"],
        ]
        update_df = self.power_user_update_df.loc[
            (self.power_user_update_df["timestamp"].dt.date < end_date)
            & (pd.notna(self.power_user_update_df["new_end_timestamp"])),
            ["last_name", "timestamp", "new_end_timestamp"],
        ]
        users = []
        for user in user_df.itertuples():
            user_rows = user_df.loc[user_df["last_name"] == user.last_name, :]
            user_row = user_rows.loc[user_rows["start_timestamp"].idxmax()]
            if user_row["start_timestamp"] != user.start_timestamp:
                continue
            updates = update_df.loc[
                (update_df["last_name"] == user.last_name)
                & (update_df["timestamp"] > user.start_timestamp),
                :,
            ]
            end_timestamp = (
                updates.loc[updates["timestamp"].idxmax()]["new_end_timestamp"].date()
                if len(updates) > 0
                else (
                    user.end_timestamp.date() if pd.notna(user.end_timestamp) else None
                )
            )
            if (end_timestamp is None) or (end_timestamp > start_date):
                users.append(
                    (
                        user.last_name,
                        user.start_timestamp.date(),
                        end_timestamp,
                    )
                )
        return users

    def enumerate_power_users(
        self, pi_last_name: str, start_date: datetime.date, end_date: datetime.date
    ) -> list[tuple[str, datetime.date, datetime.date]]:
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
        out_list = []
        for name in out_df.loc[
            out_df["start_timestamp"].dt.date <= end_date, "last_name"
        ]:
            for term in self.describe_user(name, start_date, end_date):
                if not term[0]:
                    continue
                out_list.append((name, term[1], term[2]))

        return sorted(out_list, key=lambda x: x[1])

    def describe_user(
        self, last_name: str, period_start: datetime.date, period_end: datetime.date
    ) -> list[tuple[bool, datetime.date | None, datetime.date | None]]:
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
        list of (bool, date or None, date or None)
            Tuples describing whether the user was a power user during each
            of their terms during the period, then if so, the start and end
            dates of those terms.
        """
        orig_row = self.power_user_df.loc[
            (self.power_user_df["last_name"] == last_name)
            & (self.power_user_df["start_timestamp"].dt.date <= period_end),
            :,
        ].copy()
        if len(orig_row) == 0:
            return [(False, None, None)]

        # Only want the most recent term
        orig_row = orig_row.loc[orig_row["start_timestamp"].idxmax()]
        relevant_updates = self.power_user_update_df.loc[
            (self.power_user_update_df["last_name"] == last_name)
            & (self.power_user_update_df["timestamp"].dt.date <= period_end)
            & (
                (self.power_user_update_df["new_end_timestamp"].notna())
                | (self.power_user_update_df["new_power_user"].notna())
            ),
            ["timestamp", "new_end_timestamp", "new_power_user"],
        ]
        # Only want updates after this term started
        relevant_updates = relevant_updates.loc[
            (
                relevant_updates["timestamp"].dt.date
                >= orig_row["start_timestamp"].date()
            ),
            :,
        ]
        for update in relevant_updates.sort_values(by=["timestamp"]).itertuples():
            if update.timestamp.date() > orig_row["end_timestamp"].date():
                orig_row = gen_new_term_from_row(orig_row, update)
            else:
                orig_row = update_term_from_row(orig_row, update)

        if not (
            pd.isna(orig_row["end_timestamp"])
            or orig_row["end_timestamp"].date() >= period_start
        ):
            return [(False, None, None)]

        return [
            (True, orig_row["start_timestamp"], orig_row["end_timestamp"])
            if orig_row["power_user"]
            else (False, None, None)
        ]


def gen_new_term_from_row(orig_row: pd.Series, update: pd.Series) -> pd.Series:
    """Update a user's entry to consider a new term."""
    orig_row["start_timestamp"] = update.timestamp
    if pd.notna(update.new_end_timestamp):
        orig_row["end_timestamp"] = update.new_end_timestamp
    else:
        print("User reinstated with no new end date")
    if pd.notna(update.new_power_user):
        if update.new_power_user:
            orig_row["power_user"] = True
        else:
            orig_row["power_user"] = False
    return orig_row


def update_term_from_row(orig_row: pd.Series, update: pd.Series):
    """Update a user's existing term."""
    if pd.notna(update.new_end_timestamp):
        orig_row["end_timestamp"] = update.new_end_timestamp
    if pd.notna(update.new_power_user):
        if update.new_power_user:
            if not orig_row["power_user"]:
                # They became a power user with the update
                orig_row["power_user"] = True
                orig_row["start_timestamp"] = update.timestamp
        elif orig_row["power_user"]:
            # They stopped being a power user at the update
            # timestamp, so update appropriately.
            orig_row["end_timestamp"] = update.timestamp
    return orig_row
