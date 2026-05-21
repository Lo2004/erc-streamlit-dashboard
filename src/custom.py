from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_loader import WindPriceData, load_wind_price_table
from src.data_loader import load_risk_free_returns
from src.erc import run_erc_backtest
from src.metrics import build_period_table


SAMPLE_CUSTOM_PATH = Path("data/测试拓展资产集.xlsx")
RISK_FREE_PATH = Path("data/无风险利率-1年期国债指数.xlsx")


def load_custom_price_data(source) -> WindPriceData:
    return load_wind_price_table(source)


def build_asset_catalog(prices: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    rows = []
    for code in prices.columns:
        series = prices[code].dropna()
        if series.empty:
            continue
        rows.append(
            {
                "代码": code,
                "名称": names.get(code, code),
                "起始日期": series.index.min(),
                "结束日期": series.index.max(),
                "有效天数": len(series),
            }
        )
    return pd.DataFrame(rows)


def available_window(prices: pd.DataFrame, selected_codes: list[str]) -> tuple[pd.Timestamp, pd.Timestamp]:
    starts = [prices[code].dropna().index.min() for code in selected_codes]
    ends = [prices[code].dropna().index.max() for code in selected_codes]
    return max(starts), min(ends)


def run_custom_backtest(
    prices: pd.DataFrame,
    selected_codes: list[str],
    benchmark_code: str,
    start_date: str,
    end_date: str,
    lookback: int,
    rebalance: str,
    rebalance_day: int = 1,
    names: dict[str, str] | None = None,
):
    if len(selected_codes) < 2:
        raise ValueError("请至少选择 2 个资产。")
    if benchmark_code not in prices.columns:
        raise ValueError("基准资产不在上传数据中。")

    common_start, common_end = available_window(prices, list(dict.fromkeys(selected_codes + [benchmark_code])))
    start = max(pd.Timestamp(start_date), common_start)
    end = min(pd.Timestamp(end_date), common_end)
    if start >= end:
        raise ValueError("所选资产在当前回测区间没有足够的共同数据。")

    required_codes = list(dict.fromkeys(selected_codes + [benchmark_code]))
    aligned_prices = prices.loc[start:end, required_codes].dropna(how="any")
    asset_prices = aligned_prices[selected_codes]
    if len(asset_prices) <= lookback + 5:
        raise ValueError("共同样本过短，请减少回看窗口或调整资产/日期。")

    result = run_erc_backtest(asset_prices, lookback=lookback, rebalance=rebalance, rebalance_day=rebalance_day)
    benchmark_name = (names or {}).get(benchmark_code, benchmark_code)
    benchmark_ret = aligned_prices[benchmark_code].pct_change().reindex(result["returns"].index).fillna(0.0)
    benchmark_nav = (1.0 + benchmark_ret).cumprod().rename(benchmark_name)

    nav_df = pd.concat([result["nav"], benchmark_nav], axis=1).dropna()
    drawdown_df = nav_df / nav_df.cummax() - 1.0
    turnover_zero = pd.Series(0.0, index=nav_df.index)
    rf_ret, rf_label = load_risk_free_returns(RISK_FREE_PATH)
    metrics = pd.concat(
        {
            "自定义ERC": build_period_table(
                result["nav"].reindex(nav_df.index),
                result["turnover"].reindex(nav_df.index),
                rf_ret=rf_ret,
                rf_label=rf_label,
            ),
            benchmark_name: build_period_table(
                benchmark_nav.reindex(nav_df.index),
                turnover_zero,
                rf_ret=rf_ret,
                rf_label=rf_label,
            ),
        },
        names=["组合", "区间"],
    )
    return {
        "asset_prices": asset_prices,
        "weights": result["weights"],
        "nav_df": nav_df,
        "drawdown_df": drawdown_df,
        "metrics": metrics,
        "common_start": common_start,
        "common_end": common_end,
        "benchmark_prices": aligned_prices[[benchmark_code]],
    }


def run_custom_backtest_with_benchmark(
    prices: pd.DataFrame,
    selected_codes: list[str],
    benchmark_code: str,
    start_date: str,
    end_date: str,
    lookback: int,
    rebalance: str,
    rebalance_day: int = 1,
    names: dict[str, str] | None = None,
):
    return run_custom_backtest(
        prices=prices,
        selected_codes=selected_codes,
        benchmark_code=benchmark_code,
        start_date=start_date,
        end_date=end_date,
        lookback=lookback,
        rebalance=rebalance,
        rebalance_day=rebalance_day,
        names=names,
    )
