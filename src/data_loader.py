from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class WindPriceData:
    prices: pd.DataFrame
    names: dict[str, str]


def load_wind_price_table(path: str | Path) -> WindPriceData:
    """Load Wind's multi-row-header price export into a code-indexed price table."""
    raw = pd.read_excel(path, sheet_name=0, header=None)
    if raw.shape[0] < 5 or raw.shape[1] < 2:
        raise ValueError("Wind table is too small. Expected four header rows plus data rows.")

    names = raw.iloc[2].tolist()
    codes = raw.iloc[3].tolist()

    data = raw.iloc[4:].copy()
    data.columns = codes
    if "Date" not in data.columns:
        raise ValueError("Wind table must include a Date column in the fourth header row.")

    data = data.rename(columns={"Date": "date"})
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"]).drop_duplicates("date").sort_values("date")

    price_cols = [col for col in data.columns if col != "date"]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    prices = data.set_index("date")[price_cols].dropna(how="all")

    code_names = {
        str(code): str(name)
        for code, name in zip(codes, names)
        if pd.notna(code) and str(code) != "Date"
    }
    return WindPriceData(prices=prices, names=code_names)


def validate_required_codes(prices: pd.DataFrame, required_codes: list[str]) -> None:
    missing = [code for code in required_codes if code not in prices.columns]
    if missing:
        raise ValueError(f"Missing required Wind code(s): {', '.join(missing)}")
