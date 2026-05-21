from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_CALENDAR_PATH = Path("data/A股交易日历_2026-2028.xlsx")


def load_trading_calendar(path: str | Path = DEFAULT_CALENDAR_PATH) -> pd.DatetimeIndex:
    path = Path(path)
    if not path.exists():
        return pd.DatetimeIndex([])

    raw = pd.read_excel(path, sheet_name=0)
    date_col = "date" if "date" in raw.columns else raw.columns[0]
    dates = pd.to_datetime(raw[date_col], errors="coerce").dropna()
    return pd.DatetimeIndex(dates.drop_duplicates().sort_values())


def next_calendar_rebalance_date(
    last_date: pd.Timestamp,
    rebalance: str,
    rebalance_day: int,
    trading_days: pd.DatetimeIndex,
) -> pd.Timestamp:
    if len(trading_days) == 0:
        return pd.NaT

    if rebalance == "D":
        future_days = trading_days[trading_days > pd.Timestamp(last_date)]
        if len(future_days) == 0:
            return pd.NaT
        return future_days[0]
    if rebalance not in {"W", "M"}:
        raise ValueError("rebalance must be 'D', 'W', or 'M'.")

    nth = max(int(rebalance_day), 1) - 1
    days = trading_days.to_series()
    periods = days.dt.to_period("M" if rebalance == "M" else "W")
    scheduled_dates = []
    for _, group in days.groupby(periods):
        if len(group) == 0:
            continue
        scheduled_dates.append(group.iloc[min(nth, len(group) - 1)])

    scheduled = pd.DatetimeIndex(scheduled_dates)
    future_schedule = scheduled[scheduled > pd.Timestamp(last_date)]
    if len(future_schedule) == 0:
        return pd.NaT
    return future_schedule[0]
