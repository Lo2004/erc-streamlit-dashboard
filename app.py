from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from src.baseline import ASSET_LABELS, DATA_PATH, compute_baseline, compute_baseline_from_prices, load_baseline_data
from src.charts import baseline_dashboard_chart, final_signal_chart, hierarchical_weights_chart
from src.custom import (
    SAMPLE_CUSTOM_PATH,
    available_window,
    build_asset_catalog,
    load_custom_price_data,
    run_custom_backtest_with_benchmark,
    run_two_layer_erc,
)
from src.risk_control import run_final_indicator_overlay

import uuid


st.set_page_config(page_title="基准 ERC 看板", layout="wide")


_HIGHER_BETTER = {"年化收益", "夏普比率", "卡玛比率", "月胜率", "日胜率", "最大回撤"}
_LOWER_BETTER = {"年化波动率", "月均换手率", "最长回撤修复期(天)"}
# 最大回撤为负值，数值越大（越接近0）越好，归入 higher
# 无风险利率指标为文本，不做加粗


def _parse_metric_val(raw) -> float | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if s == "NA":
        return None
    try:
        return float(s.replace("%", ""))
    except ValueError:
        return None


def render_metric_block(title: str, source: pd.DataFrame, columns: list[str]) -> None:
    st.markdown(f"##### {title}")
    table = source.loc[:, columns].copy()
    groups = table.index.get_level_values("组合").unique()
    periods = table.index.get_level_values("区间").unique()

    # Determine best group per (period, column)
    best_group: dict[tuple[str, str], str] = {}
    for col in columns:
        direction = "higher" if col in _HIGHER_BETTER else ("lower" if col in _LOWER_BETTER else None)
        if direction is None:
            continue
        for period in periods:
            candidates: list[tuple[float, str]] = []
            for group in groups:
                try:
                    raw_val = table.loc[(group, period), col]
                    v = _parse_metric_val(raw_val)
                    if v is not None:
                        candidates.append((v, group))
                except (KeyError, TypeError):
                    pass
            if candidates:
                if direction == "higher":
                    best_group[(period, col)] = max(candidates, key=lambda x: x[0])[1]
                else:
                    best_group[(period, col)] = min(candidates, key=lambda x: x[0])[1]

    html = [
        """
        <style>
        .metric-table {
            width: 100%;
            border-collapse: collapse;
            border: 1px solid #e5e7eb;
            font-size: 14px;
        }
        .metric-table th {
            background: #f6f7f9;
            color: #4b5563;
            font-weight: 600;
            text-align: center;
            padding: 8px 10px;
            border: 1px solid #e5e7eb;
            white-space: nowrap;
        }
        .metric-table td {
            padding: 8px 10px;
            border: 1px solid #edf0f2;
            text-align: center;
            white-space: nowrap;
        }
        .metric-table .group-cell {
            background: #fbfbfc;
            font-weight: 600;
            color: #111827;
            vertical-align: middle;
            min-width: 90px;
        }
        .metric-table .period-cell {
            color: #4b5563;
            min-width: 72px;
        }
        .metric-table .best {
            font-weight: 700;
        }
        </style>
        <table class="metric-table">
        """
    ]
    header = "<tr><th>组合</th><th>区间</th>" + "".join(f"<th>{escape(col)}</th>" for col in columns) + "</tr>"
    html.append(header)

    for group in groups:
        group_table = table.loc[group]
        row_count = len(group_table)
        for i, (period, row) in enumerate(group_table.iterrows()):
            cells = []
            if i == 0:
                cells.append(f'<td class="group-cell" rowspan="{row_count}">{escape(str(group))}</td>')
            cells.append(f'<td class="period-cell">{escape(str(period))}</td>')
            for col in columns:
                raw = str(row[col])
                if best_group.get((period, col)) == group:
                    cells.append(f'<td class="best">{escape(raw)}</td>')
                else:
                    cells.append(f"<td>{escape(raw)}</td>")
            html.append("<tr>" + "".join(cells) + "</tr>")

    html.append("</table>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_plain_table(source: pd.DataFrame) -> None:
    html = [
        """
        <style>
        .plain-table {
            width: 100%;
            border-collapse: collapse;
            border: 1px solid #e5e7eb;
            font-size: 14px;
            margin: 8px 0 16px;
        }
        .plain-table th {
            background: #f6f7f9;
            color: #4b5563;
            font-weight: 600;
            text-align: left;
            padding: 8px 10px;
            border: 1px solid #e5e7eb;
            white-space: nowrap;
        }
        .plain-table td {
            padding: 8px 10px;
            border: 1px solid #edf0f2;
            white-space: nowrap;
        }
        .plain-table td.number-cell {
            text-align: right;
        }
        </style>
        <table class="plain-table">
        """
    ]
    html.append("<tr>" + "".join(f"<th>{escape(str(col))}</th>" for col in source.columns) + "</tr>")
    for _, row in source.iterrows():
        cells = []
        for value in row:
            cell_class = "number-cell" if isinstance(value, (int, float)) and not pd.isna(value) else ""
            cells.append(f'<td class="{cell_class}">{escape(str(value))}</td>')
        html.append("<tr>" + "".join(cells) + "</tr>")
    html.append("</table>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_sharpe_note() -> None:
    st.caption(
        "夏普比率口径：使用中债-总财富(1年以下)指数(CBA00311.CS)的日收益率作为无风险收益率，"
        "按组合/基准日收益率减无风险收益率后的超额收益计算。"
    )


@st.cache_data(show_spinner=False)
def cached_compute_baseline(path: str, start_date: str, lookback: int, rebalance: str, rebalance_day: int, cost_bps: float):
    return compute_baseline(path, start_date, lookback, rebalance, rebalance_day, cost_bps=cost_bps)


@st.cache_data(show_spinner=False)
def cached_compute_baseline_upload(uploaded_file, start_date: str, lookback: int, rebalance: str, rebalance_day: int, cost_bps: float):
    prices, names = load_baseline_data(uploaded_file)
    return compute_baseline_from_prices(prices, names, start_date, lookback, rebalance, rebalance_day, cost_bps=cost_bps)


@st.cache_data(show_spinner=False)
def cached_load_custom(path_or_file) -> tuple[pd.DataFrame, dict[str, str]]:
    loaded = load_custom_price_data(path_or_file)
    return loaded.prices, loaded.names


@st.cache_data(show_spinner=False)
def cached_final_risk_control(
    panel: pd.DataFrame,
    weights: pd.DataFrame,
    erc_nav: pd.Series,
    rebalance: str,
    rebalance_day: int,
    pc1_window: int,
    pc1_ma_window: int,
    pc1_mean_window: int,
    dsv_window: int,
    final_ma_window: int,
    mid_threshold: float,
    high_threshold: float,
    mid_cash: float,
    high_cash: float,
):
    asset_returns = panel[["stock", "bond10", "gold_hedged"]].pct_change().dropna()
    csi300_returns = panel["csi300"].pct_change().reindex(asset_returns.index).fillna(0.0)
    return run_final_indicator_overlay(
        asset_returns=asset_returns,
        erc_weights=weights,
        erc_nav=erc_nav,
        benchmark_returns=csi300_returns,
        rebalance=rebalance,
        rebalance_day=rebalance_day,
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


@st.cache_data(show_spinner=False)
def cached_nested_risk_control(
    asset_returns: pd.DataFrame,
    erc_weights: pd.DataFrame,
    erc_nav: pd.Series,
    benchmark_returns: pd.Series,
    rebalance: str,
    rebalance_day: int,
    pc1_window: int,
    pc1_ma_window: int,
    pc1_mean_window: int,
    dsv_window: int,
    final_ma_window: int,
    mid_threshold: float,
    high_threshold: float,
    mid_cash: float,
    high_cash: float,
    benchmark_name: str = "沪深300",
):
    return run_final_indicator_overlay(
        asset_returns=asset_returns,
        erc_weights=erc_weights,
        erc_nav=erc_nav,
        benchmark_returns=benchmark_returns,
        rebalance=rebalance,
        rebalance_day=rebalance_day,
        benchmark_name=benchmark_name,
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


# ────────────────────────── 自定义 ERC 风控 cached 函数 ──────────────────────────


@st.cache_data(show_spinner=False)
def cached_custom_final_risk_control(
    asset_prices: pd.DataFrame,
    benchmark_prices: pd.DataFrame,
    weights: pd.DataFrame,
    erc_nav: pd.Series,
    rebalance: str,
    rebalance_day: int,
    pc1_window: int,
    pc1_ma_window: int,
    pc1_mean_window: int,
    dsv_window: int,
    final_ma_window: int,
    mid_threshold: float,
    high_threshold: float,
    mid_cash: float,
    high_cash: float,
):
    asset_returns = asset_prices.pct_change().dropna()
    benchmark_returns = benchmark_prices.pct_change().reindex(asset_returns.index).fillna(0.0).squeeze()
    common_idx = asset_returns.index.intersection(weights.index).intersection(erc_nav.index)
    asset_returns = asset_returns.reindex(common_idx).dropna()
    weights = weights.reindex(common_idx).ffill()
    erc_nav = erc_nav.reindex(common_idx).dropna()
    benchmark_returns = benchmark_returns.reindex(common_idx).fillna(0.0)
    return run_final_indicator_overlay(
        asset_returns=asset_returns,
        erc_weights=weights,
        erc_nav=erc_nav,
        benchmark_returns=benchmark_returns,
        rebalance=rebalance,
        rebalance_day=rebalance_day,
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


# ────────────────────────── 风控面板渲染函数 ──────────────────────────


def render_tail_risk_panel(signals: pd.DataFrame, exposure: pd.Series, overlay_result: dict, asset_labels: dict) -> None:
    """Render 尾部风险 tab content. Must be called inside a tab/container context."""
    latest_signal_date = overlay_result["latest_signal_date"]
    previous_signal_date = overlay_result["previous_signal_date"]

    if pd.isna(latest_signal_date):
        st.warning("当前样本不足以形成有效 Final 风险强度，请延长样本。")
        return

    latest_strength = signals.loc[latest_signal_date, "final_strength"]
    latest_exposure = exposure.loc[latest_signal_date]
    if pd.notna(previous_signal_date):
        prev_strength = signals.loc[previous_signal_date, "final_strength"]
        prev_exposure = exposure.loc[previous_signal_date]
        strength_delta = latest_strength - prev_strength
        exposure_delta = latest_exposure - prev_exposure
    else:
        strength_delta = None
        exposure_delta = None

    st.subheader("风险状态")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("最新风控信号日", latest_signal_date.strftime("%Y-%m-%d"))
    f2.metric(
        "Final强度",
        f"{latest_strength:.2f}",
        delta=None if strength_delta is None else f"{strength_delta:+.2f}",
        delta_color="inverse",
    )
    f3.metric(
        "目标总仓位",
        f"{latest_exposure:.2%}",
        delta=None if exposure_delta is None else f"{exposure_delta:+.2%}",
    )
    f4.metric("现金仓位", f"{1.0 - latest_exposure:.2%}")
    st.caption(
        "尾部风险口径：Final = PC1强度(MA30/Mean252) × 下行半方差GM63；"
        "Final强度 = Final / Final_MA252。目标现金仓位按侧边栏阈值与现金仓位参数分层生成；"
        "现金收益固定为 0，执行仓位次一交易日生效。"
    )

    factor_latest = pd.DataFrame(
        [
            {"指标": "Final指标", "数值": signals.loc[latest_signal_date, "final_indicator"]},
            {"指标": "Final_MA252", "数值": signals.loc[latest_signal_date, "final_ma"]},
            {"指标": "PC1强度(MA30/Mean252)", "数值": signals.loc[latest_signal_date, "pc1_strength"]},
            {"指标": "下行半方差GM63", "数值": signals.loc[latest_signal_date, "gm_dsv"]},
        ]
    ).assign(数值=lambda df: df["数值"].map(lambda x: "NA" if pd.isna(x) else f"{x:.6f}"))
    render_plain_table(factor_latest)
    st.plotly_chart(final_signal_chart(signals, exposure), width="stretch")

    st.subheader("尾部风险增强表现")
    risk_labels = {**asset_labels, "cash": "现金(收益=0)"}
    st.plotly_chart(
        baseline_dashboard_chart(
            overlay_result["nav_df"],
            overlay_result["drawdown_df"],
            overlay_result["weights"],
            risk_labels,
        ),
        width="stretch",
    )
    st.subheader("尾部风险核心指标")
    render_sharpe_note()
    render_metric_block("收益与风险", overlay_result["metrics"], ["年化收益", "年化波动率", "夏普比率", "卡玛比率"])
    render_metric_block("回撤", overlay_result["metrics"], ["最大回撤", "最大回撤开始时间", "最大回撤结束时间", "最长回撤修复期(天)"])
    render_metric_block("交易与胜率", overlay_result["metrics"], ["月均换手率", "月胜率", "日胜率"])


col_title, col_dl = st.columns([3, 1])
with col_title:
    st.title("ERC 组合看板")
with col_dl:
    st.markdown("<br>", unsafe_allow_html=True)

    @st.cache_data(show_spinner=False)
    def _build_report_zip() -> bytes:
        import zipfile, io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            files = [
                ("data/ERC风险平价组合 - 风险控制策略.pdf", "ERC风险平价组合 - 风险控制策略.pdf"),
                ("docs/summary_report.pdf", "风险平价组合策略回测总结报告.pdf"),
            ]
            for path, arcname in files:
                p = Path(path)
                if p.exists():
                    zf.writestr(arcname, p.read_bytes())
        return buf.getvalue()

    report_zip = _build_report_zip()
    st.download_button(
        "下载原始报告（ZIP）",
        data=report_zip,
        file_name="ERC全套报告.zip",
        mime="application/zip",
        use_container_width=True,
    )
with st.sidebar:
    st.header("参数")
    start_date = st.date_input("回测起点", value=pd.Timestamp("2010-01-01"))
    lookback = st.number_input("ERC回看窗口（日）", min_value=20, max_value=252, value=60, step=5)
    rebalance_label = st.radio("调仓频率", ["月度", "周度", "日度"], horizontal=True)
    rebalance_map = {"月度": "M", "周度": "W", "日度": "D"}
    rebalance = rebalance_map[rebalance_label]
    if rebalance == "D":
        rebalance_day = 1
        st.caption("日度调仓：每个交易日更新权重，次一交易日生效。")
    else:
        period_label = "每月" if rebalance == "M" else "每周"
        max_day = 23 if rebalance == "M" else 5
        rebalance_day = st.number_input(
            f"{period_label}第几个交易日调仓",
            min_value=1,
            max_value=max_day,
            value=1,
            step=1,
        )
        st.caption(f"{period_label}第 {rebalance_day} 个交易日计算新权重，次一交易日生效；若当期交易日不足，则使用当期最后一个交易日。")

    cost_bps = st.number_input("双边交易成本（bps）", min_value=0, max_value=500, value=0, step=1)
    st.caption("非 0 时从组合日收益中扣除：成本 × 日换手率。默认 0 不启用。")

    with st.expander("尾部风险参数", expanded=False):
        risk_defaults = {
            "risk_pc1_window": 63,
            "risk_pc1_ma_window": 30,
            "risk_pc1_mean_window": 252,
            "risk_dsv_window": 63,
            "risk_final_ma_window": 252,
            "risk_mid_threshold": 1.20,
            "risk_high_threshold": 1.50,
            "risk_mid_cash_pct": 25,
            "risk_high_cash_pct": 50,
        }
        for key, val in risk_defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val
        if st.button("默认", key="reset_risk_defaults", help="恢复所有尾部风险参数为默认值"):
            for key, val in risk_defaults.items():
                st.session_state[key] = val
        pc1_window = st.number_input("PC1窗口（日）", min_value=20, max_value=252, value=st.session_state.risk_pc1_window, step=1, key="risk_pc1_window")
        pc1_ma_window = st.number_input("PC1平滑窗口（日）", min_value=5, max_value=126, value=st.session_state.risk_pc1_ma_window, step=1, key="risk_pc1_ma_window")
        pc1_mean_window = st.number_input("PC1历史均值窗口（日）", min_value=60, max_value=756, value=st.session_state.risk_pc1_mean_window, step=21, key="risk_pc1_mean_window")
        dsv_window = st.number_input("下行半方差窗口（日）", min_value=20, max_value=252, value=st.session_state.risk_dsv_window, step=1, key="risk_dsv_window")
        final_ma_window = st.number_input("Final均线窗口（日）", min_value=60, max_value=756, value=st.session_state.risk_final_ma_window, step=21, key="risk_final_ma_window")
        mid_threshold = st.number_input("中风险阈值", min_value=0.10, max_value=5.00, value=st.session_state.risk_mid_threshold, step=0.05, format="%.2f", key="risk_mid_threshold")
        mid_current = float(mid_threshold)
        high_threshold = st.number_input("高风险阈值", min_value=mid_current, max_value=8.00, value=max(1.50, mid_current, float(st.session_state.risk_high_threshold)), step=0.05, format="%.2f", key="risk_high_threshold")
        mid_cash_pct = st.slider("中风险现金仓位", min_value=0, max_value=100, value=st.session_state.risk_mid_cash_pct, step=5, key="risk_mid_cash_pct")
        high_cash_pct = st.slider("高风险现金仓位", min_value=0, max_value=100, value=st.session_state.risk_high_cash_pct, step=5, key="risk_high_cash_pct")

baseline_upload = None

page_baseline, page_custom = st.tabs(["基准 ERC", "自定义 ERC"])

with page_baseline:
    st.subheader("基准 ERC")
    update_box = st.expander("手动更新基准数据", expanded=False)
    with update_box:
        st.write("下载当前 Wind 模板，在本地用安装 Wind 插件的 Excel 打开并刷新数据，再把刷新后的 Excel 上传回来。")
        if DATA_PATH.exists():
            st.download_button(
                "下载当前基准 Wind Excel",
                data=DATA_PATH.read_bytes(),
                file_name=DATA_PATH.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.warning(f"找不到默认数据文件：{DATA_PATH}")
        baseline_upload = st.file_uploader(
            "上传刷新后的基准 Wind Excel",
            type=["xlsx", "xls"],
            key="baseline_update_file",
        )
        st.caption("必须包含 H20955.CSI、CBA00661.CS、CI005213.WI、H00300.CSI、AU9999.SGE。上传文件只在当前会话中使用。")

    try:
        cost_bps_f = float(cost_bps)
        if baseline_upload is not None:
            data = cached_compute_baseline_upload(baseline_upload, str(start_date), int(lookback), rebalance, int(rebalance_day), cost_bps_f)
            baseline_source_label = baseline_upload.name
        elif DATA_PATH.exists():
            data = cached_compute_baseline(str(DATA_PATH), str(start_date), int(lookback), rebalance, int(rebalance_day), cost_bps_f)
            baseline_source_label = str(DATA_PATH)
        else:
            raise FileNotFoundError(f"找不到数据文件：{DATA_PATH}")
    except Exception as exc:
        data = None
        baseline_error = exc
    else:
        baseline_error = None

    if baseline_error is not None:
        st.error(f"基准组合计算失败：{baseline_error}")
    else:
        nav_df = data["nav_df"]
        weights = data["weights"]
        metrics = data["metrics"]
        hedge_stats = data["hedge_stats"]

        latest_date = nav_df.index.max()
        latest_weight_values = weights.iloc[-1].rename(index=ASSET_LABELS)
        latest_weight_changes = data["weight_change"].rename(index=ASSET_LABELS)
        last_rebalance_date = data["last_rebalance_date"]
        next_rebalance_date = data["next_rebalance_date"]
        last_rebalance_text = "NA" if pd.isna(last_rebalance_date) else last_rebalance_date.strftime("%Y-%m-%d")
        next_rebalance_text = "NA" if pd.isna(next_rebalance_date) else next_rebalance_date.strftime("%Y-%m-%d")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("最新日期", latest_date.strftime("%Y-%m-%d"))
        col2.metric("ERC净值", f"{nav_df['ERC'].iloc[-1]:.2f}")
        col3.metric("60/40净值", f"{nav_df['60/40基准'].iloc[-1]:.2f}")
        col4.metric("沪深300净值", f"{nav_df['沪深300'].iloc[-1]:.2f}")

        reb_col1, reb_col2, reb_col3 = st.columns([1, 1, 2])
        reb_col1.metric("上次调仓日", last_rebalance_text)
        reb_col2.metric("下次调仓日", next_rebalance_text)
        reb_col3.caption("调仓日按当前频率与第几个交易日设置估算；权重在调仓计算日后的下一交易日生效。")

        hold_col1, hold_col2, hold_col3 = st.columns(3)
        for col, (name, value) in zip([hold_col1, hold_col2, hold_col3], latest_weight_values.items()):
            change = latest_weight_changes.get(name, 0.0)
            col.metric(f"最新持仓 | {name}", f"{value:.2%}", delta=f"{change:+.2%}")

        st.caption(
            "基准口径：红利低波100全收益 + 中债10年以上国债总财富 + 黄金(中信，对冲沪深300 beta)；"
            "对比基准为 60% 沪深300收益 + 40% 中债10年以上国债总财富；"
            f"净值起算日为 {nav_df.index.min().strftime('%Y-%m-%d')}。"
        )

        tab_overview, tab_tail_risk, tab_data = st.tabs(["表现", "尾部风险", "数据"])

        with tab_overview:
            st.plotly_chart(baseline_dashboard_chart(nav_df, data["drawdown_df"], weights, ASSET_LABELS), width="stretch")
            st.subheader("核心指标")
            render_sharpe_note()
            render_metric_block("收益与风险", metrics, ["年化收益", "年化波动率", "夏普比率", "卡玛比率"])
            render_metric_block("回撤", metrics, ["最大回撤", "最大回撤开始时间", "最大回撤结束时间", "最长回撤修复期(天)"])
            render_metric_block("交易与胜率", metrics, ["月均换手率", "月胜率", "日胜率"])

        with tab_tail_risk:
            try:
                final_risk_data = cached_final_risk_control(
                    data["panel"],
                    weights,
                    nav_df["ERC"],
                    rebalance,
                    int(rebalance_day),
                    int(pc1_window),
                    int(pc1_ma_window),
                    int(pc1_mean_window),
                    int(dsv_window),
                    int(final_ma_window),
                    float(mid_threshold),
                    float(high_threshold),
                    float(mid_cash_pct) / 100.0,
                    float(high_cash_pct) / 100.0,
                )
            except Exception as exc:
                st.error(f"尾部风险计算失败：{exc}")
            else:
                render_tail_risk_panel(final_risk_data["signals"], final_risk_data["exposure"], final_risk_data, ASSET_LABELS)

        with tab_data:
            st.subheader("数据状态")
            st.write(f"当前数据：`{baseline_source_label}`")
            st.write(f"样本区间：`{nav_df.index.min().strftime('%Y-%m-%d')}` 至 `{latest_date.strftime('%Y-%m-%d')}`")
            st.write(
                "黄金对冲回归系数："
                f"`beta_CSI300={hedge_stats['beta_equity']:.4f}`，"
                f"`beta_AU9999={hedge_stats['beta_spot_gold']:.4f}`"
            )
            render_plain_table(data["panel"].tail(10).reset_index().assign(date=lambda df: df["date"].dt.strftime("%Y-%m-%d")))

with page_custom:
    st.subheader("自定义 ERC")
    if SAMPLE_CUSTOM_PATH.exists():
        st.download_button(
            "下载自定义 Wind 模板",
            data=SAMPLE_CUSTOM_PATH.read_bytes(),
            file_name=SAMPLE_CUSTOM_PATH.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    uploaded_file = st.file_uploader("上传 Wind 标准化收盘价 Excel", type=["xlsx", "xls"])

    try:
        if uploaded_file is not None:
            custom_prices, custom_names = cached_load_custom(uploaded_file)
            data_label = uploaded_file.name
        else:
            custom_prices, custom_names = cached_load_custom(str(SAMPLE_CUSTOM_PATH))
            data_label = str(SAMPLE_CUSTOM_PATH)
    except Exception as exc:
        st.error(f"读取自定义资产数据失败：{exc}")
        st.stop()

    catalog = build_asset_catalog(custom_prices, custom_names)
    if catalog.empty:
        st.warning("没有识别到可用资产。")
        st.stop()

    st.caption(f"当前数据：{data_label}")
    render_plain_table(
        catalog.assign(
            起始日期=lambda df: df["起始日期"].dt.strftime("%Y-%m-%d"),
            结束日期=lambda df: df["结束日期"].dt.strftime("%Y-%m-%d"),
        )
    )

    # ── Mode toggle ──
    if "erc_mode" not in st.session_state:
        st.session_state.erc_mode = "基础"
    erc_mode = st.radio("ERC模式", ["基础", "嵌套"], horizontal=True, key="erc_mode")

    if erc_mode == "基础":
        label_by_code = {row["代码"]: f"{row['名称']} | {row['代码']}" for _, row in catalog.iterrows()}
        default_codes = catalog["代码"].head(min(3, len(catalog))).tolist()
        selected_codes = st.multiselect(
            "选择纳入 ERC 的资产",
            options=catalog["代码"].tolist(),
            default=default_codes,
            format_func=lambda code: label_by_code.get(code, code),
        )
        benchmark_default = "H00300.CSI" if "H00300.CSI" in catalog["代码"].tolist() else catalog["代码"].iloc[0]
        benchmark_code = st.selectbox(
            "选择对比基准资产",
            options=catalog["代码"].tolist(),
            index=catalog["代码"].tolist().index(benchmark_default),
            format_func=lambda code: label_by_code.get(code, code),
        )

        if len(selected_codes) >= 2:
            common_start, common_end = available_window(custom_prices, list(dict.fromkeys(selected_codes + [benchmark_code])))
            st.info(f"所选资产共同可用区间：{common_start.strftime('%Y-%m-%d')} 至 {common_end.strftime('%Y-%m-%d')}")
            custom_col1, custom_col2, custom_col3 = st.columns([1, 1, 1])
            custom_start = custom_col1.date_input("自定义回测起点", value=common_start, min_value=common_start, max_value=common_end)
            custom_end = custom_col2.date_input("自定义回测终点", value=common_end, min_value=common_start, max_value=common_end)
            run_button = custom_col3.button("开始计算", type="primary", width="stretch")
        else:
            st.warning("请至少选择 2 个资产。")
            run_button = False

        if run_button:
            try:
                custom_result = run_custom_backtest_with_benchmark(
                    prices=custom_prices,
                    selected_codes=selected_codes,
                    benchmark_code=benchmark_code,
                    start_date=str(custom_start),
                    end_date=str(custom_end),
                    lookback=int(lookback),
                    rebalance=rebalance,
                    rebalance_day=int(rebalance_day),
                    names=custom_names,
                    cost_bps=float(cost_bps),
                )
            except Exception as exc:
                st.error(f"自定义组合计算失败：{exc}")
            else:
                selected_labels = {code: custom_names.get(code, code) for code in selected_codes}
                benchmark_name = custom_names.get(benchmark_code, benchmark_code)
                custom_nav = custom_result["nav_df"]
                custom_weights = custom_result["weights"]
                latest_custom_weights = custom_weights.iloc[-1].rename(index=selected_labels)

                c1, c2, c3 = st.columns(3)
                c1.metric("起算日", custom_nav.index.min().strftime("%Y-%m-%d"))
                c2.metric("截止日", custom_nav.index.max().strftime("%Y-%m-%d"))
                c3.metric("组合净值", f"{custom_nav['ERC'].iloc[-1]:.2f}")

                st.caption(
                    f"实际计算区间为 {custom_nav.index.min().strftime('%Y-%m-%d')} 至 {custom_nav.index.max().strftime('%Y-%m-%d')}；"
                    f"对比基准为 {benchmark_name}。"
                )

                tab_overview, tab_tail_risk = st.tabs(["表现", "尾部风险"])

                with tab_overview:
                    st.plotly_chart(
                        baseline_dashboard_chart(
                            custom_nav,
                            custom_result["drawdown_df"],
                            custom_weights,
                            selected_labels,
                        ),
                        width="stretch",
                    )

                    st.subheader("核心指标")
                    render_sharpe_note()
                    render_metric_block("收益与风险", custom_result["metrics"], ["年化收益", "年化波动率", "夏普比率", "卡玛比率"])
                    render_metric_block("回撤", custom_result["metrics"], ["最大回撤", "最大回撤开始时间", "最大回撤结束时间", "最长回撤修复期(天)"])
                    render_metric_block("交易与胜率", custom_result["metrics"], ["月均换手率", "月胜率", "日胜率"])

                    st.subheader("最新一期持仓")
                    render_plain_table(
                        latest_custom_weights.rename_axis("资产")
                        .reset_index(name="最新权重")
                        .assign(最新权重=lambda df: df["最新权重"].map(lambda x: f"{x:.2%}"))
                    )

                with tab_tail_risk:
                    try:
                        custom_tail_risk = cached_custom_final_risk_control(
                            custom_result["asset_prices"],
                            custom_result["benchmark_prices"],
                            custom_result["weights"],
                            custom_nav["ERC"],
                            rebalance, int(rebalance_day),
                            int(pc1_window),
                            int(pc1_ma_window),
                            int(pc1_mean_window),
                            int(dsv_window),
                            int(final_ma_window),
                            float(mid_threshold),
                            float(high_threshold),
                            float(mid_cash_pct) / 100.0,
                            float(high_cash_pct) / 100.0,
                        )
                    except Exception as exc:
                        st.error(f"尾部风险计算失败：{exc}")
                    else:
                        metric_idx = custom_tail_risk["metrics"].index
                        old_level = metric_idx.levels[metric_idx.names.index("组合")]
                        new_level = pd.Index([benchmark_name if v == "沪深300" else v for v in old_level])
                        custom_tail_risk["metrics"].index = metric_idx.set_levels(new_level, level="组合")
                        custom_tail_risk["nav_df"].rename(columns={"沪深300": benchmark_name}, inplace=True)
                        custom_tail_risk["drawdown_df"].rename(columns={"沪深300": benchmark_name}, inplace=True)
                        render_tail_risk_panel(
                            custom_tail_risk["signals"], custom_tail_risk["exposure"],
                            custom_tail_risk, selected_labels,
                        )
    else:
        # ── Nested mode ──
        code_list = catalog["代码"].tolist()
        asset_options = {code: custom_names.get(code, code) for code in code_list}

        st.markdown("##### 可用资产池")
        st.markdown('<style>.asset-tag{display:inline-block;background:#f4f5f8;border:1px solid #dce0e8;border-radius:6px;padding:5px 12px;margin:4px 6px 4px 0;font-size:13px;white-space:nowrap;transition:background .15s}.asset-tag:hover{background:#e8ebf1}.asset-tag .code{color:#8e94a0;font-size:11px;margin-left:4px}</style>', unsafe_allow_html=True)
        tag_html = "".join(
            f'<span class="asset-tag">{asset_options[code]} <span class="code">({code})</span></span>'
            for code in code_list
        )
        st.markdown(f'<div style="line-height:2.4">{tag_html}</div>', unsafe_allow_html=True)

        st.markdown("---")

        # Initialize nested groups
        if "nested_groups" not in st.session_state:
            st.session_state.nested_groups = []

        col_groups, col_bench = st.columns([3, 1])
        with col_groups:
            st.markdown("##### 大组定义")

            # Render each group
            to_delete = None
            for gi, group in enumerate(st.session_state.nested_groups):
                gid = group["id"]
                with st.container(border=True):
                    gcols = st.columns([3, 1])
                    with gcols[0]:
                        gname = st.text_input(
                            "组名",
                            value=group.get("name", f"大组{gi+1}"),
                            key=f"gname_{gid}",
                        )
                    with gcols[1]:
                        if st.button("删除大组", key=f"del_{gid}"):
                            to_delete = gid
                    g_assets = st.multiselect(
                        "资产",
                        options=code_list,
                        default=[c for c in group.get("assets", []) if c in code_list],
                        format_func=lambda c: asset_options.get(c, c),
                        key=f"gassets_{gid}",
                    )
                    # Persist to session_state
                    group["name"] = gname
                    group["assets"] = g_assets

            if to_delete is not None:
                st.session_state.nested_groups = [
                    g for g in st.session_state.nested_groups if g["id"] != to_delete
                ]
                st.rerun()

            if st.button("+ 添加大组", use_container_width=True):
                import uuid as _uuid
                st.session_state.nested_groups.append({
                    "id": str(_uuid.uuid4()),
                    "name": f"大组{len(st.session_state.nested_groups)+1}",
                    "assets": [],
                })
                st.rerun()

        with col_bench:
            st.markdown("##### 对比基准")
            benchmark_default = "H00300.CSI" if "H00300.CSI" in code_list else code_list[0]
            bm_default_idx = code_list.index(benchmark_default) if benchmark_default in code_list else 0
            benchmark_code = st.selectbox(
                "基准资产",
                options=code_list,
                index=bm_default_idx,
                format_func=lambda c: asset_options.get(c, c),
                key="nested_benchmark",
            )

        # Date range & run
        all_group_codes = list(dict.fromkeys(
            code for g in st.session_state.nested_groups for code in g.get("assets", [])
        ))
        has_valid_groups = len(st.session_state.nested_groups) >= 2 and len(all_group_codes) > 0

        if has_valid_groups:
            needed = list(dict.fromkeys(all_group_codes + [benchmark_code]))
            n_common_start, n_common_end = available_window(custom_prices, needed)
            nest_col1, nest_col2, nest_col3 = st.columns([1, 1, 1])
            nested_start = nest_col1.date_input(
                "回测起点", value=n_common_start,
                min_value=n_common_start, max_value=n_common_end,
                key="nested_start",
            )
            nested_end = nest_col2.date_input(
                "回测终点", value=n_common_end,
                min_value=n_common_start, max_value=n_common_end,
                key="nested_end",
            )
            run_nested = nest_col3.button("开始计算", type="primary", width="stretch", key="run_nested")
        else:
            st.warning("请至少定义 2 个大组，并为大组添加资产。")
            run_nested = False

        @st.cache_resource
        def _nested_cache():
            return type("_Cache", (), {"result": None, "benchmark_name": None})()

        _cache = _nested_cache()

        if run_nested and has_valid_groups:
            try:
                _cache.result = run_two_layer_erc(
                    prices=custom_prices,
                    groups=st.session_state.nested_groups,
                    benchmark_code=benchmark_code,
                    start_date=str(nested_start),
                    end_date=str(nested_end),
                    lookback=int(lookback),
                    rebalance=rebalance,
                    rebalance_day=int(rebalance_day),
                    names=custom_names,
                    cost_bps=float(cost_bps),
                )
                _cache.benchmark_name = custom_names.get(benchmark_code, benchmark_code)
            except Exception as exc:
                st.error(f"两层 ERC 计算失败：{exc}")
                _cache.result = None

        if _cache.result is not None:
            nested_result = _cache.result
            benchmark_name = _cache.benchmark_name
            n_nav = nested_result["nav_df"]
            n_dd = nested_result["drawdown_df"]
            n_metrics = nested_result["metrics"]
            n_eff_w = nested_result["effective_weights"]
            n_group_w = nested_result["group_weights"]
            n_group_navs = nested_result["group_navs"]

            # Build label mapping
            all_used_codes = list(n_eff_w.columns)
            n_labels = {code: custom_names.get(code, code) for code in all_used_codes}

            # Build group assignments for chart coloring
            group_assignments: dict[str, list[str]] = {}
            for g in st.session_state.nested_groups:
                gname = g["name"] or "未命名"
                codes_in = [c for c in (g.get("assets") or []) if c in all_used_codes]
                if codes_in:
                    group_assignments[gname] = codes_in

            n_col1, n_col2, n_col3 = st.columns(3)
            n_col1.metric("起算日", n_nav.index.min().strftime("%Y-%m-%d"))
            n_col2.metric("截止日", n_nav.index.max().strftime("%Y-%m-%d"))
            n_col3.metric("两层ERC净值", f"{n_nav['两层ERC'].iloc[-1]:.2f}")

            st.caption(
                f"实际计算区间为 {n_nav.index.min().strftime('%Y-%m-%d')} 至 {n_nav.index.max().strftime('%Y-%m-%d')}；"
                f"对比基准为 {benchmark_name}。"
            )

            nest_tab1, nest_tab2, nest_tab3 = st.tabs(["表现", "两层权重", "尾部风险"])

            with nest_tab1:
                st.plotly_chart(
                    baseline_dashboard_chart(n_nav, n_dd, n_eff_w, n_labels),
                    width="stretch",
                )
                st.subheader("核心指标")
                render_sharpe_note()
                render_metric_block("收益与风险", n_metrics, ["年化收益", "年化波动率", "夏普比率", "卡玛比率"])
                render_metric_block("回撤", n_metrics, ["最大回撤", "最大回撤开始时间", "最大回撤结束时间", "最长回撤修复期(天)"])
                render_metric_block("交易与胜率", n_metrics, ["月均换手率", "月胜率", "日胜率"])

            with nest_tab2:
                st.plotly_chart(
                    hierarchical_weights_chart(n_eff_w, group_assignments, n_labels),
                    width="stretch",
                )
                st.subheader("大组间权重")
                render_plain_table(
                    n_group_w.rename_axis("日期").iloc[-1:].T.reset_index()
                    .rename(columns={"index": "大组", n_group_w.index[-1]: "权重"})
                    .assign(**{"权重": lambda df: df["权重"].map(lambda x: f"{x:.2%}")})
                )

            with nest_tab3:
                tail_method = st.radio(
                    "尾部风险信号计算口径",
                    ["按全部入选资产（不分组）", "按大组（每组视为一个资产）"],
                    horizontal=True,
                    key="nested_tail_method",
                )

                # Build common tail-risk inputs
                bm_ret_all = nested_result["asset_prices"][benchmark_code].pct_change()
                erc_nav_s = n_nav["两层ERC"]

                if tail_method == "按全部入选资产（不分组）":
                    asset_codes_for_tail = list(n_eff_w.columns)
                    tail_prices = nested_result["asset_prices"][asset_codes_for_tail]
                    tail_returns = tail_prices.pct_change().dropna()
                    tail_weights = n_eff_w
                    tail_labels = n_labels
                else:
                    group_ret_dict = {}
                    group_weights_for_tail = {}
                    for gname, grets in nested_result["group_returns"].items():
                        group_ret_dict[gname] = grets
                    tail_returns = pd.DataFrame(group_ret_dict).dropna()
                    tail_weights = n_group_w.reindex(tail_returns.index).ffill()
                    tail_labels = {g: g for g in nested_result["group_names"]}

                try:
                    nested_tail = cached_nested_risk_control(
                        asset_returns=tail_returns,
                        erc_weights=tail_weights,
                        erc_nav=erc_nav_s,
                        benchmark_returns=bm_ret_all,
                        rebalance=rebalance,
                        rebalance_day=int(rebalance_day),
                        pc1_window=int(pc1_window),
                        pc1_ma_window=int(pc1_ma_window),
                        pc1_mean_window=int(pc1_mean_window),
                        dsv_window=int(dsv_window),
                        final_ma_window=int(final_ma_window),
                        mid_threshold=float(mid_threshold),
                        high_threshold=float(high_threshold),
                        mid_cash=float(mid_cash_pct) / 100.0,
                        high_cash=float(high_cash_pct) / 100.0,
                        benchmark_name=benchmark_name,
                    )
                except Exception as exc:
                    st.error(f"尾部风险计算失败：{exc}")
                else:
                    # Replace the default "沪深300" label with the actual benchmark name
                    mt_idx = nested_tail["metrics"].index
                    old_lvl = mt_idx.levels[mt_idx.names.index("组合")]
                    new_lvl = pd.Index([benchmark_name if v == "沪深300" else v for v in old_lvl])
                    nested_tail["metrics"].index = mt_idx.set_levels(new_lvl, level="组合")
                    nested_tail["nav_df"].rename(columns={"沪深300": benchmark_name}, inplace=True)
                    nested_tail["drawdown_df"].rename(columns={"沪深300": benchmark_name}, inplace=True)
                    render_tail_risk_panel(
                        nested_tail["signals"], nested_tail["exposure"],
                        nested_tail, tail_labels,
                    )
