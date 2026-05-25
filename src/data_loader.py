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


def load_risk_free_returns(
    path: str | Path,
    code: str | None = None,
) -> tuple[pd.Series, pd.Series, str]:
    """
    加载无风险利率数据。兼容两种 Wind 导出格式：

    - 标准多资产格式（names → row 2, codes → row 3, 含 Date 列）
    - 单资产导出格式（name → row 0, code → row 1, 列名为 日期/收盘价/Date/close）

    Returns (rf_daily_return, rf_nav, rf_label).
    """
    raw = pd.read_excel(path, sheet_name=0, header=None)
    if raw.shape[0] < 5 or raw.shape[1] < 2:
        raise ValueError("Risk-free rate data file is too small.")

    # 从文件头提取真实的指数名称/代码（row 0/1）
    header_name = None
    header_code = None
    row0 = [str(v) for v in raw.iloc[0].tolist() if pd.notna(v)]
    row1 = [str(v) for v in raw.iloc[1].tolist() if pd.notna(v)]
    if len(row0) >= 2 and row0[0] == "nan":
        header_name = row0[1]
    elif len(row0) >= 1:
        header_name = row0[0]
    if len(row1) >= 2 and row1[0] == "nan":
        header_code = row1[1]
    elif len(row1) >= 1:
        header_code = row1[0]

    # 读取数据
    row3 = [str(v) for v in raw.iloc[3].tolist()]
    row3_non_date = [v for v in row3 if v not in ("nan", "Date")]
    if len(row3_non_date) == 1 and row3_non_date[0] == "close":
        # 单资产导出格式（Date + close 两列）
        data = raw.iloc[4:].copy()
        data.columns = [str(v) for v in row3]

        if "Date" in data.columns:
            data = data.rename(columns={"Date": "date"})
        elif "date" not in data.columns:
            data = data.rename(columns={data.columns[0]: "date"})

        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).drop_duplicates("date").sort_values("date")

        price_col = None
        for c in data.columns:
            if c == "date":
                continue
            s = pd.to_numeric(data[c], errors="coerce")
            if s.notna().sum() > 0:
                price_col = c
                break

        if price_col is None:
            raise ValueError("No price column found in risk-free rate data.")

        data[price_col] = pd.to_numeric(data[price_col], errors="coerce")
        nav = data.set_index("date")[price_col].dropna()
        target_code = code or header_code or price_col
        rf_label = f"{header_name or '无风险利率'}({target_code})"
    else:
        # 标准 Wind 多列格式
        loaded = load_wind_price_table(path)
        target_code = code if (code and code in loaded.prices.columns) else loaded.prices.columns[0]
        nav = loaded.prices[target_code].dropna()
        rf_label = f"{loaded.names.get(target_code, target_code)}({target_code})"

    # 若 header 提取到了更精确的名称，覆盖标签
    if header_name and header_code:
        rf_label = f"{header_name}({header_code})"

    rf_ret = nav.pct_change().fillna(0.0).rename("rf_ret")
    return rf_ret, nav.rename("rf_nav"), rf_label


RF_CODE = "CBA00621.CS"


def extract_rf_from_prices(
    prices: pd.DataFrame,
    names: dict[str, str] | None = None,
) -> tuple[pd.Series, pd.Series, str]:
    """从合并价格 DataFrame 中提取无风险利率列。"""
    if RF_CODE not in prices.columns:
        raise ValueError(f"价格数据中缺少无风险利率列: {RF_CODE}")
    nav = prices[RF_CODE].dropna()
    name = (names or {}).get(RF_CODE, RF_CODE)
    rf_label = f"{name}({RF_CODE})"
    rf_ret = nav.pct_change().fillna(0.0).rename("rf_ret")
    return rf_ret, nav.rename("rf_nav"), rf_label
