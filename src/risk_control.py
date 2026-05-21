from __future__ import annotations

import numpy as np
import pandas as pd

from src.data_loader import load_risk_free_returns
from src.erc import compute_rebalance_schedule
from src.metrics import build_period_table

RISK_FREE_PATH = "data/无风险利率-1年期国债指数.xlsx"

def rolling_pc1_cov_explained(returns: pd.DataFrame, window: int = 63) -> pd.Series:
    out = pd.Series(np.nan, index=returns.index, name=f"pc1_{window}")
    for end_pos in range(window - 1, len(returns)):
        win = returns.iloc[end_pos - window + 1 : end_pos + 1].dropna()
        if len(win) < window or win.shape[1] < 2:
            continue
        cov = win.cov().values
        eigvals = np.linalg.eigvalsh(cov)
        total = float(np.sum(eigvals))
        if np.isfinite(total) and total > 0:
            out.iloc[end_pos] = float(eigvals[-1] / total)
    return out


def rolling_dsv(series: pd.Series, window: int = 63, min_periods: int = 32) -> pd.Series:
    return series.clip(upper=0.0).pow(2).rolling(window=window, min_periods=min_periods).mean()


def build_final_signals(
    asset_returns: pd.DataFrame,
    erc_returns: pd.Series,
    pc1_window: int = 63,
    pc1_ma_window: int = 30,
    pc1_mean_window: int = 252,
    dsv_window: int = 63,
    final_ma_window: int = 252,
    mid_threshold: float = 1.2,
    high_threshold: float = 1.5,
    mid_cash: float = 0.25,
    high_cash: float = 0.50,
) -> pd.DataFrame:
    pc1 = rolling_pc1_cov_explained(asset_returns, window=pc1_window)
    pc1_ma = pc1.rolling(pc1_ma_window, min_periods=max(1, pc1_ma_window // 2)).mean()
    pc1_mean = pc1_ma.rolling(pc1_mean_window, min_periods=max(1, pc1_mean_window // 2)).mean()
    pc1_strength = pc1_ma / pc1_mean

    erc_dsv = rolling_dsv(erc_returns.reindex(asset_returns.index), window=dsv_window, min_periods=max(2, dsv_window // 2))
    asset_dsv = asset_returns.apply(lambda col: rolling_dsv(col, window=dsv_window, min_periods=max(2, dsv_window // 2)))
    sum_dsv = asset_dsv.sum(axis=1)
    gm_dsv = np.sqrt(erc_dsv.clip(lower=0.0) * sum_dsv.clip(lower=0.0))

    final_indicator = pc1_strength * gm_dsv
    final_ma = final_indicator.rolling(final_ma_window, min_periods=max(1, final_ma_window // 2)).mean()
    final_strength = final_indicator / final_ma

    return pd.DataFrame(
        {
            "risk_score": final_strength,
            "final_strength": final_strength,
            "final_indicator": final_indicator,
            "final_ma": final_ma,
            "pc1": pc1,
            "pc1_ma": pc1_ma,
            "pc1_strength": pc1_strength,
            "erc_dsv": erc_dsv,
            "sum_dsv": sum_dsv,
            "gm_dsv": gm_dsv,
            "cash_target": _cash_target_from_strength(
                final_strength,
                mid_threshold=mid_threshold,
                high_threshold=high_threshold,
                mid_cash=mid_cash,
                high_cash=high_cash,
            ),
        },
        index=asset_returns.index,
    )


def _cash_target_from_strength(
    strength: pd.Series,
    mid_threshold: float = 1.2,
    high_threshold: float = 1.5,
    mid_cash: float = 0.25,
    high_cash: float = 0.50,
) -> pd.Series:
    cash_target = pd.Series(0.0, index=strength.index, name="目标现金仓位")
    mid_cash = float(np.clip(mid_cash, 0.0, 1.0))
    high_cash = float(np.clip(high_cash, 0.0, 1.0))
    cash_target[(strength >= mid_threshold) & (strength < high_threshold)] = mid_cash
    cash_target[strength >= high_threshold] = high_cash
    return cash_target


def build_threshold_exposure(
    signals: pd.DataFrame,
    rebalance: str = "M",
    rebalance_day: int = 1,
) -> tuple[pd.Series, pd.DatetimeIndex]:
    target_exposure = (1.0 - signals["cash_target"]).clip(0.0, 1.0).rename("目标总仓位")
    target_exposure = target_exposure.ffill().fillna(1.0)
    schedule = compute_rebalance_schedule(target_exposure.index, rebalance=rebalance, rebalance_day=rebalance_day)
    if len(schedule) == 0:
        return target_exposure, schedule

    flags = pd.Series(False, index=target_exposure.index)
    flags.loc[schedule.intersection(target_exposure.index)] = True
    exposure = target_exposure.where(flags).ffill().fillna(1.0).rename("目标总仓位")
    return exposure, schedule


def _build_overlay_result(
    asset_returns: pd.DataFrame,
    erc_weights: pd.DataFrame,
    erc_nav: pd.Series,
    benchmark_returns: pd.Series,
    signals: pd.DataFrame,
    exposure: pd.Series,
    signal_schedule: pd.DatetimeIndex,
    benchmark_name: str = "沪深300",
) -> dict[str, pd.DataFrame | pd.Series | pd.Timestamp]:
    exposure_lag = exposure.shift(1).fillna(exposure.iloc[0])
    risk_weights = erc_weights.mul(exposure_lag, axis=0)
    risk_weights["cash"] = 1.0 - exposure_lag
    risk_returns = (risk_weights[asset_returns.columns] * asset_returns).sum(axis=1).rename("ERC+风控增强")
    risk_nav = (1.0 + risk_returns).cumprod().rename("ERC+风控增强")
    benchmark_nav = (1.0 + benchmark_returns).cumprod().rename(benchmark_name)

    nav_df = pd.concat([erc_nav.rename("ERC基准"), risk_nav, benchmark_nav], axis=1).dropna()
    drawdown_df = nav_df / nav_df.cummax() - 1.0
    weights = risk_weights.reindex(nav_df.index).dropna()
    turnover_erc = (erc_weights.diff().abs().sum(axis=1) / 2.0).reindex(nav_df.index).fillna(0.0)
    turnover_risk = (risk_weights.diff().abs().sum(axis=1) / 2.0).reindex(nav_df.index).fillna(0.0)
    turnover_zero = pd.Series(0.0, index=nav_df.index)
    rf_ret, rf_label = load_risk_free_returns(RISK_FREE_PATH)

    metrics = pd.concat(
        {
            "ERC基准": build_period_table(nav_df["ERC基准"], turnover_erc, rf_ret=rf_ret, rf_label=rf_label),
            "ERC+风控增强": build_period_table(nav_df["ERC+风控增强"], turnover_risk, rf_ret=rf_ret, rf_label=rf_label),
            benchmark_name: build_period_table(nav_df[benchmark_name], turnover_zero, rf_ret=rf_ret, rf_label=rf_label),
        },
        names=["组合", "区间"],
    )

    valid_signal_dates = signal_schedule.intersection(signals.dropna(subset=["risk_score"]).index)
    valid_signal_dates = valid_signal_dates[valid_signal_dates <= signals.index.max()]
    latest_signal_date = valid_signal_dates[-1] if len(valid_signal_dates) else signals["risk_score"].last_valid_index()
    previous_signal_date = valid_signal_dates[-2] if len(valid_signal_dates) > 1 else pd.NaT

    return {
        "signals": signals,
        "exposure": exposure,
        "weights": weights,
        "nav_df": nav_df,
        "drawdown_df": drawdown_df,
        "metrics": metrics,
        "latest_signal_date": latest_signal_date,
        "previous_signal_date": previous_signal_date,
    }


def run_final_indicator_overlay(
    asset_returns: pd.DataFrame,
    erc_weights: pd.DataFrame,
    erc_nav: pd.Series,
    benchmark_returns: pd.Series,
    rebalance: str = "M",
    rebalance_day: int = 1,
    benchmark_name: str = "沪深300",
    pc1_window: int = 63,
    pc1_ma_window: int = 30,
    pc1_mean_window: int = 252,
    dsv_window: int = 63,
    final_ma_window: int = 252,
    mid_threshold: float = 1.2,
    high_threshold: float = 1.5,
    mid_cash: float = 0.25,
    high_cash: float = 0.50,
) -> dict[str, pd.DataFrame | pd.Series | pd.Timestamp]:
    idx = asset_returns.index.intersection(erc_weights.index).intersection(erc_nav.index).intersection(benchmark_returns.index)
    asset_returns = asset_returns.reindex(idx).fillna(0.0)
    erc_weights = erc_weights.reindex(idx).ffill().fillna(1.0 / asset_returns.shape[1])
    erc_nav = erc_nav.reindex(idx).dropna()
    benchmark_returns = benchmark_returns.reindex(idx).fillna(0.0)

    idx = idx.intersection(erc_nav.index)
    asset_returns = asset_returns.reindex(idx)
    erc_weights = erc_weights.reindex(idx)
    benchmark_returns = benchmark_returns.reindex(idx)
    erc_returns = (erc_weights * asset_returns).sum(axis=1).rename("ERC")

    signals = build_final_signals(
        asset_returns=asset_returns,
        erc_returns=erc_returns,
        pc1_window=pc1_window,
        pc1_ma_window=pc1_ma_window,
        pc1_mean_window=pc1_mean_window,
        dsv_window=dsv_window,
        final_ma_window=final_ma_window,
        mid_threshold=mid_threshold,
        high_threshold=high_threshold,
        mid_cash=mid_cash,
        high_cash=high_cash,
    )
    exposure, signal_schedule = build_threshold_exposure(signals, rebalance=rebalance, rebalance_day=rebalance_day)
    return _build_overlay_result(
        asset_returns=asset_returns,
        erc_weights=erc_weights,
        erc_nav=erc_nav,
        benchmark_returns=benchmark_returns,
        signals=signals,
        exposure=exposure,
        signal_schedule=signal_schedule,
        benchmark_name=benchmark_name,
    )
