from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_loader import load_wind_price_table, validate_required_codes
from src.erc import hedge_gold_series, run_erc_backtest
from src.metrics import build_period_table


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


def load_baseline_data(path: str | Path) -> tuple[pd.DataFrame, dict[str, str]]:
    loaded = load_wind_price_table(path)
    required = [CODE_STOCK, CODE_BOND10, CODE_GOLD, CODE_CSI300, CODE_AU9999]
    validate_required_codes(loaded.prices, required)
    return loaded.prices, loaded.names


def compute_baseline(path: str | Path, start_date: str, lookback: int, rebalance: str):
    prices, names = load_baseline_data(path)
    return compute_baseline_from_prices(prices, names, start_date, lookback, rebalance)


def compute_baseline_from_prices(
    prices: pd.DataFrame,
    names: dict[str, str],
    start_date: str,
    lookback: int,
    rebalance: str,
):
    prices = prices.loc[prices.index >= pd.Timestamp(start_date)].dropna()

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
    )

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
            "ERC": build_period_table(result["nav"].reindex(nav_df.index), result["turnover"].reindex(nav_df.index)),
            "60/40基准": build_period_table(bench_nav.reindex(nav_df.index), turnover_zero),
            "沪深300": build_period_table(csi300_nav.reindex(nav_df.index), turnover_zero),
        },
        names=["组合", "区间"],
    )

    return {
        "names": names,
        "panel": panel,
        "weights": result["weights"].reindex(nav_df.index).dropna(),
        "nav_df": nav_df,
        "drawdown_df": drawdown_df,
        "metrics": metrics,
        "hedge_stats": hedge_stats,
    }
