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


def compute_rf_rates_per_period(
    rf_nav: pd.Series,
    nav_index: pd.DatetimeIndex,
) -> dict[str, str]:
    """计算各标准区间的年化无风险收益率，用于 Sharpe 说明文字。"""
    end_date = nav_index.max()
    periods = {
        "全样本": nav_index.min(),
        "近10年": end_date - pd.DateOffset(years=10),
        "近5年": end_date - pd.DateOffset(years=5),
        "近2年": end_date - pd.DateOffset(years=2),
        "近1年": end_date - pd.DateOffset(years=1),
        "近6个月": end_date - pd.DateOffset(months=6),
    }
    freq = detect_freq(nav_index)
    rates = {}
    for label, start in periods.items():
        mask = nav_index >= start
        period_idx = nav_index[mask]
        if len(period_idx) < 2:
            rates[label] = "NA"
            continue
        # 用 method="ffill" 确保即使首日 rf_nav 无数据也能取到前序值
        rf_aligned = rf_nav.reindex(period_idx, method="ffill")
        n = len(rf_aligned)
        if rf_aligned.iloc[0] <= 0 or rf_aligned.iloc[-1] <= 0:
            rates[label] = "NA"
            continue
        ann_rf = (rf_aligned.iloc[-1] / rf_aligned.iloc[0]) ** (freq / n) - 1.0
        rates[label] = f"{ann_rf * 100:.2f}%"
    return rates


def max_dd_info(nav: pd.Series) -> tuple[float, pd.Timestamp, pd.Timestamp]:
    dd = nav / nav.cummax() - 1.0
    end = dd.idxmin()
    start = nav.loc[:end].idxmax()
    return float(dd.min()), start, end


def longest_recovery_days(nav: pd.Series, rec_cutoff: pd.Timestamp | None = None) -> int:
    """
    最长回撤修复天数（仅统计已完成的修复，未完成的回撤不计入）。

    Parameters
    ----------
    nav : pd.Series
        净值序列（应包含足够的历史上下文以确定正确的初始峰值）。
    rec_cutoff : Timestamp, optional
        若指定，只统计修复完成日期 >= rec_cutoff 的修复段。
    """
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
                if rec_cutoff is None or idx[i] >= rec_cutoff:
                    longest = max(longest, (idx[i] - peak_t).days)
                in_drawdown = False
            peak_val = vals[i]
            peak_t = idx[i]
        else:
            in_drawdown = True

    return int(longest)


def calc_metrics(
    nav: pd.Series,
    turnover: pd.Series,
    rf_ret: pd.Series | None = None,
    rf_label: str = "未设置(按0处理)",
    rec_nav: pd.Series | None = None,
    rec_cutoff: pd.Timestamp | None = None,
    rf_nav: pd.Series | None = None,
) -> dict[str, str]:
    nav = nav.dropna()
    if len(nav) < 20:
        return {key: "NA" for key in METRIC_COLUMNS}

    freq = detect_freq(nav.index)
    ret = nav.pct_change().dropna()
    ann_ret = (nav.iloc[-1] / nav.iloc[0]) ** (freq / len(nav)) - 1.0
    ann_vol = ret.std() * np.sqrt(freq)

    # 夏普比率 = (组合年化收益 - 同期无风险年化收益) / 年化波动率
    if rf_nav is not None:
        rf_aligned = rf_nav.reindex(nav.index, method="ffill")
        n = len(rf_aligned)
        if rf_aligned.iloc[0] > 0 and n >= 2:
            rf_ann_ret = (rf_aligned.iloc[-1] / rf_aligned.iloc[0]) ** (freq / n) - 1.0
        else:
            rf_ann_ret = 0.0
    else:
        rf_ann_ret = 0.0
    sharpe = (ann_ret - rf_ann_ret) / ann_vol if ann_vol > 0 else np.nan

    mdd, mdd_start, mdd_end = max_dd_info(nav)
    calmar = ann_ret / abs(mdd) if mdd < 0 else np.nan
    monthly_turn = turnover.reindex(nav.index).resample("ME").sum().mean()
    monthly_ret = nav.resample("ME").last().pct_change().dropna()

    # 修复期计算使用完整上下文净值（rec_nav）以确立正确的初始峰值
    rec_nav_actual = rec_nav if rec_nav is not None else nav
    longest_rec = longest_recovery_days(rec_nav_actual, rec_cutoff=rec_cutoff)

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
        "最长回撤修复期(天)": f"{longest_rec}",
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
    rf_nav: pd.Series | None = None,
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
        nav_slice = nav.loc[mask]
        if label == "全样本":
            rows[label] = calc_metrics(
                nav_slice, turnover.loc[mask],
                rf_ret=rf_ret, rf_label=rf_label, rf_nav=rf_nav,
                rec_nav=nav_slice, rec_cutoff=None,
            )
        else:
            rows[label] = calc_metrics(
                nav_slice, turnover.loc[mask],
                rf_ret=rf_ret, rf_label=rf_label, rf_nav=rf_nav,
                rec_nav=nav.loc[:nav_slice.index[-1]],
                rec_cutoff=start,
            )
    return pd.DataFrame(rows).T[METRIC_COLUMNS]
