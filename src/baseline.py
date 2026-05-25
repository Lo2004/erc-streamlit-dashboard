from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_loader import load_wind_price_table, validate_required_codes
from src.data_loader import RF_CODE, extract_rf_from_prices
from src.erc import compute_rebalance_schedule
from src.erc import hedge_gold_series, run_erc_backtest
from src.metrics import build_period_table
from src.trading_calendar import load_trading_calendar, next_calendar_rebalance_date


DATA_PATH = Path("data/标准 ERC- 收盘价数据.xlsx")

CODE_STOCK = "H20955.CSI"
CODE_BOND10 = "CBA00661.CS"
CODE_GOLD = "CI005213.WI"
CODE_CSI300 = "H00300.CSI"
CODE_AU9999 = "AU9999.SGE"

ASSET_LABELS = {
    "stock": "红利低波100全收益",
    "bond10": "中债国债总财富(10年以上)",
    "gold_hedged": "黄金(中信，对冲沪深300 beta)",
}


def estimate_next_rebalance_date(last_date: pd.Timestamp, rebalance: str, rebalance_day: int) -> pd.Timestamp:
    trading_days = load_trading_calendar()
    calendar_date = next_calendar_rebalance_date(last_date, rebalance, rebalance_day, trading_days)
    if pd.notna(calendar_date):
        return calendar_date

    if rebalance == "D":
        return last_date + pd.offsets.BDay(1)

    nth = max(int(rebalance_day), 1) - 1
    if rebalance == "M":
        month_start = (last_date + pd.offsets.MonthBegin(1)).normalize()
        month_end = (month_start + pd.offsets.MonthEnd(0)).normalize()
        future_index = pd.bdate_range(month_start, month_end)
    elif rebalance == "W":
        next_week_start = (last_date + pd.offsets.Week(weekday=0)).normalize()
        next_week_end = next_week_start + pd.Timedelta(days=4)
        future_index = pd.bdate_range(next_week_start, next_week_end)
    else:
        raise ValueError("rebalance must be 'D', 'W', or 'M'.")

    if len(future_index) == 0:
        return pd.NaT
    return future_index[min(nth, len(future_index) - 1)]


def load_baseline_data(path: str | Path) -> tuple[pd.DataFrame, dict[str, str]]:
    loaded = load_wind_price_table(path)
    required = [CODE_STOCK, CODE_BOND10, CODE_GOLD, CODE_CSI300, CODE_AU9999, RF_CODE]
    validate_required_codes(loaded.prices, required)
    return loaded.prices, loaded.names


def compute_baseline(path: str | Path, start_date: str, lookback: int, rebalance: str, rebalance_day: int = 1, cost_bps: float = 0):
    prices, names = load_baseline_data(path)
    return compute_baseline_from_prices(prices, names, start_date, lookback, rebalance, rebalance_day, cost_bps=cost_bps)


def compute_baseline_from_prices(
    prices: pd.DataFrame,
    names: dict[str, str],
    start_date: str,
    lookback: int,
    rebalance: str,
    rebalance_day: int = 1,
    cost_bps: float = 0,
):
    prices = prices.loc[prices.index >= pd.Timestamp(start_date)].dropna()

    rf_ret, rf_nav, rf_label = extract_rf_from_prices(prices, names)

    gold_hedged, hedge_stats = hedge_gold_series(
        prices,
        gold_code=CODE_GOLD,
        equity_code=CODE_CSI300,
        spot_gold_code=CODE_AU9999,
    )

    panel = pd.concat(
        [
            prices[CODE_STOCK].rename("stock"),
            prices[CODE_BOND10].rename("bond10"),
            gold_hedged.rename("gold_hedged"),
            prices[CODE_CSI300].rename("csi300"),
        ],
        axis=1,
        join="inner",
    ).dropna()

    result = run_erc_backtest(
        panel[["stock", "bond10", "gold_hedged"]],
        lookback=lookback,
        rebalance=rebalance,
        rebalance_day=rebalance_day,
        cost_bps=cost_bps,
    )
    rebalance_dates = result["rebalance_dates"]

    csi300_ret = panel["csi300"].pct_change().reindex(result["returns"].index).fillna(0.0)
    bond_ret = panel["bond10"].pct_change().reindex(result["returns"].index).fillna(0.0)
    bench_ret = 0.6 * csi300_ret + 0.4 * bond_ret

    bench_nav = (1.0 + bench_ret).cumprod().rename("60/40基准")
    csi300_nav = (1.0 + csi300_ret).cumprod().rename("沪深300")
    nav_df = pd.concat([result["nav"], bench_nav, csi300_nav], axis=1).dropna()

    drawdown_df = nav_df / nav_df.cummax() - 1.0
    turnover_zero = pd.Series(0.0, index=nav_df.index)
    metrics = pd.concat(
        {
            "ERC": build_period_table(
                result["nav"].reindex(nav_df.index),
                result["turnover"].reindex(nav_df.index),
                rf_ret=rf_ret,
                rf_label=rf_label, rf_nav=rf_nav,
            ),
            "60/40基准": build_period_table(bench_nav.reindex(nav_df.index), turnover_zero, rf_ret=rf_ret, rf_label=rf_label, rf_nav=rf_nav),
            "沪深300": build_period_table(csi300_nav.reindex(nav_df.index), turnover_zero, rf_ret=rf_ret, rf_label=rf_label, rf_nav=rf_nav),
        },
        names=["组合", "区间"],
    )

    weight_change = pd.Series(0.0, index=result["weights"].columns)
    last_rebalance_date = pd.NaT
    next_rebalance_date = pd.NaT
    effective_rebalance_dates = pd.DatetimeIndex([])
    if len(rebalance_dates) > 0:
        effective_dates = []
        for date in rebalance_dates:
            pos = panel.index.get_loc(date)
            if pos + 1 < len(panel.index):
                effective_dates.append(panel.index[pos + 1])
        effective_rebalance_dates = pd.DatetimeIndex(effective_dates)
        effective_rebalance_dates = effective_rebalance_dates[effective_rebalance_dates.isin(result["weights"].index)]
        past_effective_dates = effective_rebalance_dates[effective_rebalance_dates <= nav_df.index.max()]
        if len(past_effective_dates) > 0:
            last_rebalance_date = past_effective_dates[-1]
            if len(past_effective_dates) > 1:
                prev_rebalance_date = past_effective_dates[-2]
                weight_change = result["weights"].loc[last_rebalance_date] - result["weights"].loc[prev_rebalance_date]
            next_rebalance_date = estimate_next_rebalance_date(nav_df.index.max(), rebalance, rebalance_day)

    return {
        "names": names,
        "panel": panel,
        "weights": result["weights"].reindex(nav_df.index).dropna(),
        "weight_change": weight_change,
        "last_rebalance_date": last_rebalance_date,
        "next_rebalance_date": next_rebalance_date,
        "effective_rebalance_dates": effective_rebalance_dates,
        "nav_df": nav_df,
        "drawdown_df": drawdown_df,
        "metrics": metrics,
        "hedge_stats": hedge_stats,
    }
