from __future__ import annotations

import numpy as np
import pandas as pd


def detect_freq(idx: pd.DatetimeIndex) -> int:
    if len(idx) < 3:
        return 252
    med_days = pd.Series(idx).diff().dt.days.dropna().median()
    if med_days <= 2:
        return 252
    if med_days <= 10:
        return 52
    return 12


def max_dd_info(nav: pd.Series) -> tuple[float, pd.Timestamp, pd.Timestamp]:
    dd = nav / nav.cummax() - 1.0
    end = dd.idxmin()
    start = nav.loc[:end].idxmax()
    return float(dd.min()), start, end


def longest_recovery_days(nav: pd.Series) -> int:
    if len(nav) < 2:
        return 0

    vals = nav.values
    idx = nav.index
    peak_val = vals[0]
    peak_t = idx[0]
    longest = 0
    in_drawdown = False

    for i in range(1, len(vals)):
        if vals[i] >= peak_val:
            if in_drawdown:
                longest = max(longest, (idx[i] - peak_t).days)
                in_drawdown = False
            peak_val = vals[i]
            peak_t = idx[i]
        else:
            in_drawdown = True

    if in_drawdown:
        longest = max(longest, (idx[-1] - peak_t).days)
    return int(longest)


def calc_metrics(
    nav: pd.Series,
    turnover: pd.Series,
    rf_ret: pd.Series | None = None,
    rf_label: str = "未设置(按0处理)",
) -> dict[str, str]:
    nav = nav.dropna()
    if len(nav) < 20:
        return {key: "NA" for key in METRIC_COLUMNS}

    freq = detect_freq(nav.index)
    ret = nav.pct_change().dropna()
    if rf_ret is None:
        rf_aligned = pd.Series(0.0, index=ret.index)
    else:
        rf_aligned = rf_ret.reindex(ret.index).ffill().fillna(0.0)
    excess_ret = ret - rf_aligned
    ann_ret = (nav.iloc[-1] / nav.iloc[0]) ** (freq / len(nav)) - 1.0
    ann_vol = ret.std() * np.sqrt(freq)
    sharpe = excess_ret.mean() / ret.std() * np.sqrt(freq) if ret.std() > 0 else np.nan
    mdd, mdd_start, mdd_end = max_dd_info(nav)
    calmar = ann_ret / abs(mdd) if mdd < 0 else np.nan
    monthly_turn = turnover.reindex(nav.index).resample("ME").sum().mean()
    monthly_ret = nav.resample("ME").last().pct_change().dropna()

    return {
        "年化收益": f"{ann_ret * 100:.2f}%",
        "年化波动率": f"{ann_vol * 100:.2f}%",
        "夏普比率": f"{sharpe:.2f}",
        "卡玛比率": f"{calmar:.2f}",
        "最大回撤": f"{mdd * 100:.2f}%",
        "最大回撤开始时间": mdd_start.strftime("%Y-%m-%d"),
        "最大回撤结束时间": mdd_end.strftime("%Y-%m-%d"),
        "月均换手率": f"{monthly_turn * 100:.2f}%",
        "月胜率": f"{(monthly_ret > 0).mean() * 100:.2f}%",
        "日胜率": f"{(ret > 0).mean() * 100:.2f}%",
        "最长回撤修复期(天)": f"{longest_recovery_days(nav)}",
        "无风险利率指标": rf_label,
    }


METRIC_COLUMNS = [
    "年化收益",
    "年化波动率",
    "夏普比率",
    "卡玛比率",
    "最大回撤",
    "最大回撤开始时间",
    "最大回撤结束时间",
    "月均换手率",
    "月胜率",
    "日胜率",
    "最长回撤修复期(天)",
    "无风险利率指标",
]


def build_period_table(
    nav: pd.Series,
    turnover: pd.Series,
    rf_ret: pd.Series | None = None,
    rf_label: str = "未设置(按0处理)",
) -> pd.DataFrame:
    end_date = nav.index.max()
    periods = {
        "全样本": nav.index.min(),
        "近10年": end_date - pd.DateOffset(years=10),
        "近5年": end_date - pd.DateOffset(years=5),
        "近2年": end_date - pd.DateOffset(years=2),
        "近1年": end_date - pd.DateOffset(years=1),
        "近6个月": end_date - pd.DateOffset(months=6),
    }
    rows = {}
    for label, start in periods.items():
        mask = nav.index >= start
        rows[label] = calc_metrics(nav.loc[mask], turnover.loc[mask], rf_ret=rf_ret, rf_label=rf_label)
    return pd.DataFrame(rows).T[METRIC_COLUMNS]
