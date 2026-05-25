from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_loader import WindPriceData, load_wind_price_table
from src.data_loader import extract_rf_from_prices
from src.erc import run_erc_backtest
from src.metrics import build_period_table


SAMPLE_CUSTOM_PATH = Path("data/自定义ERC-默认数据集.xlsx")
_BASELINE_PATH = Path("data/标准 ERC- 收盘价数据.xlsx")


def _load_default_rf() -> tuple[pd.Series, pd.Series, str]:
    """从合并基准文件中加载无风险利率数据。"""
    loaded = load_wind_price_table(_BASELINE_PATH)
    return extract_rf_from_prices(loaded.prices, loaded.names)


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
    cost_bps: float = 0,
):
    if len(selected_codes) < 2:
        raise ValueError("请至少选择 2 个资产。")
    if benchmark_code not in prices.columns:
        raise ValueError("基准资产不在上传数据中。")

    common_start, common_end = available_window(prices, selected_codes)
    start = max(pd.Timestamp(start_date), common_start)
    end = min(pd.Timestamp(end_date), common_end)
    if start >= end:
        raise ValueError("所选资产在当前回测区间没有足够的共同数据。")

    asset_prices = prices.loc[start:end, selected_codes].dropna(how="any")
    if len(asset_prices) <= lookback + 5:
        raise ValueError("共同样本过短，请减少回看窗口或调整资产/日期。")

    result = run_erc_backtest(asset_prices, lookback=lookback, rebalance=rebalance, rebalance_day=rebalance_day, cost_bps=cost_bps)
    benchmark_name = (names or {}).get(benchmark_code, benchmark_code)
    benchmark_ret = prices[benchmark_code].reindex(asset_prices.index).pct_change().reindex(result["returns"].index).fillna(0.0)
    benchmark_nav = (1.0 + benchmark_ret).cumprod().rename(benchmark_name)

    nav_df = pd.concat([result["nav"], benchmark_nav], axis=1).dropna()
    drawdown_df = nav_df / nav_df.cummax() - 1.0
    turnover_zero = pd.Series(0.0, index=nav_df.index)
    rf_ret, rf_nav, rf_label = _load_default_rf()
    metrics = pd.concat(
        {
            "自定义ERC": build_period_table(
                result["nav"].reindex(nav_df.index),
                result["turnover"].reindex(nav_df.index),
                rf_ret=rf_ret,
                rf_label=rf_label, rf_nav=rf_nav,
            ),
            benchmark_name: build_period_table(
                benchmark_nav.reindex(nav_df.index),
                turnover_zero,
                rf_ret=rf_ret,
                rf_label=rf_label, rf_nav=rf_nav,
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
        "benchmark_prices": prices.loc[asset_prices.index, [benchmark_code]],
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
    cost_bps: float = 0,
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
        cost_bps=cost_bps,
    )


def run_two_layer_erc(
    prices: pd.DataFrame,
    groups: list[dict],
    benchmark_code: str,
    start_date: str,
    end_date: str,
    lookback: int,
    rebalance: str,
    rebalance_day: int = 1,
    names: dict[str, str] | None = None,
    cost_bps: float = 0,
):
    """
    两层 ERC 回测。

    Parameters
    ----------
    groups : list[dict]
        [{"name": "权益", "assets": [code, ...]}, ...]
        同一资产可出现在多个大组。

    Returns
    -------
    dict with keys:
        nav_df, drawdown_df, metrics — for final result vs benchmark
        group_navs — each group's standalone NAV (dict of Series)
        group_weights — final between-group weights (DataFrame)
        effective_weights — each original asset's net weight (DataFrame)
        asset_prices — aligned price panel for all assets
    """
    from src.erc import run_erc_backtest

    if not groups or all(len(g["assets"]) == 0 for g in groups):
        raise ValueError("请至少为一个大组添加资产。")
    if benchmark_code not in prices.columns:
        raise ValueError("基准资产不在上传数据中。")

    benchmark_name = (names or {}).get(benchmark_code, benchmark_code)

    # Collect all unique asset codes across groups
    all_asset_codes = list(dict.fromkeys(code for g in groups for code in g["assets"]))

    # Align common date window — from ERC assets only
    common_start, common_end = available_window(prices, all_asset_codes)
    start = max(pd.Timestamp(start_date), common_start)
    end = min(pd.Timestamp(end_date), common_end)
    if start >= end:
        raise ValueError("所选资产在当前回测区间没有足够的共同数据。")

    aligned = prices.loc[start:end, all_asset_codes].dropna(how="any")
    if len(aligned) <= lookback + 5:
        raise ValueError("共同样本过短，请减少回看窗口或调整资产/日期。")

    # ── Layer 1: within-group ERC ──
    group_returns: dict[str, pd.Series] = {}
    group_weights: dict[str, pd.DataFrame] = {}
    group_navs: dict[str, pd.Series] = {}

    for g in groups:
        gname = g["name"]
        codes = [c for c in g["assets"] if c in aligned.columns]
        if len(codes) == 0:
            continue

        if len(codes) == 1:
            col = codes[0]
            px = aligned[col]
            ret = px.pct_change().dropna()
            g_ret_idx = ret.index.intersection(aligned.index)
            group_returns[gname] = ret.reindex(g_ret_idx)
            group_weights[gname] = pd.DataFrame({col: 1.0}, index=g_ret_idx)
            group_navs[gname] = (1.0 + ret.reindex(g_ret_idx)).cumprod()
        else:
            sub_prices = aligned[codes]
            res = run_erc_backtest(sub_prices, lookback=lookback, rebalance=rebalance, rebalance_day=rebalance_day, cost_bps=0)
            ret = res["returns"]
            g_ret_idx = ret.index.intersection(aligned.index)
            group_returns[gname] = ret.reindex(g_ret_idx)
            group_weights[gname] = res["weights"].reindex(g_ret_idx).ffill()
            group_navs[gname] = (1.0 + ret.reindex(g_ret_idx)).cumprod()

    if len(group_returns) < 2:
        raise ValueError("两层 ERC 要求至少 2 个大组（当前 %d 个）。" % len(group_returns))

    # ── Layer 2: between-group ERC ──
    group_price_panel = pd.concat(
        {gname: gnv for gname, gnv in group_navs.items()},
        axis=1, join="inner",
    ).dropna()

    layer2 = run_erc_backtest(group_price_panel, lookback=lookback, rebalance=rebalance, rebalance_day=rebalance_day, cost_bps=0)
    l2_weights = layer2["weights"]

    # ── Effective weights: asset-level net weight = layer2_weight * sub_weight ──
    common_eff_idx = l2_weights.index
    effective_weights = pd.DataFrame(0.0, index=common_eff_idx, columns=all_asset_codes)

    for g in groups:
        gname = g["name"]
        if gname not in l2_weights.columns or gname not in group_weights:
            continue
        sub_w = group_weights[gname].reindex(common_eff_idx).ffill().fillna(0.0)
        for code in sub_w.columns:
            if code in effective_weights.columns:
                effective_weights[code] += l2_weights[gname] * sub_w[code]

    # ── Final NAV & benchmark ──
    asset_returns = aligned[all_asset_codes].pct_change().reindex(effective_weights.index).dropna(how="any")
    effective_weights = effective_weights.reindex(asset_returns.index)
    final_turnover = (effective_weights.diff().abs().sum(axis=1) / 2.0).fillna(0.0).rename("turnover")
    final_ret = (effective_weights * asset_returns).sum(axis=1).rename("两层ERC")
    if cost_bps > 0:
        final_ret = final_ret - (cost_bps / 10000.0) * final_turnover
    final_nav = (1.0 + final_ret).cumprod().rename("两层ERC")

    benchmark_ret = prices[benchmark_code].reindex(aligned.index).pct_change().reindex(final_nav.index).fillna(0.0)
    benchmark_nav = (1.0 + benchmark_ret).cumprod().rename(benchmark_name)

    nav_df = pd.concat([final_nav, benchmark_nav], axis=1).dropna()
    drawdown_df = nav_df / nav_df.cummax() - 1.0
    turnover_zero = pd.Series(0.0, index=nav_df.index)
    rf_ret, rf_nav, rf_label = _load_default_rf()
    metrics = pd.concat(
        {
            "两层ERC": build_period_table(
                final_nav.reindex(nav_df.index),
                final_turnover.reindex(nav_df.index),
                rf_ret=rf_ret,
                rf_label=rf_label, rf_nav=rf_nav,
            ),
            benchmark_name: build_period_table(
                benchmark_nav.reindex(nav_df.index),
                turnover_zero,
                rf_ret=rf_ret,
                rf_label=rf_label, rf_nav=rf_nav,
            ),
        },
        names=["组合", "区间"],
    )

    return {
        "group_names": list(group_returns.keys()),
        "nav_df": nav_df,
        "drawdown_df": drawdown_df,
        "metrics": metrics,
        "group_navs": group_navs,
        "effective_weights": effective_weights,
        "group_weights": l2_weights,
        "asset_prices": aligned,
        "group_returns": group_returns,
        "turnover": final_turnover,
    }
