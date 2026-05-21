from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from src.baseline import ASSET_LABELS, DATA_PATH, compute_baseline, compute_baseline_from_prices, load_baseline_data
from src.charts import baseline_dashboard_chart, drawdown_chart, nav_chart, weights_chart
from src.custom import (
    SAMPLE_CUSTOM_PATH,
    available_window,
    build_asset_catalog,
    load_custom_price_data,
    run_custom_backtest_with_benchmark,
)


st.set_page_config(page_title="基准 ERC 看板", layout="wide")


def render_metric_block(title: str, source: pd.DataFrame, columns: list[str]) -> None:
    st.markdown(f"##### {title}")
    table = source.loc[:, columns].copy()
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
        </style>
        <table class="metric-table">
        """
    ]
    header = "<tr><th>组合</th><th>区间</th>" + "".join(f"<th>{escape(col)}</th>" for col in columns) + "</tr>"
    html.append(header)

    for group in table.index.get_level_values("组合").unique():
        group_table = table.loc[group]
        row_count = len(group_table)
        for i, (period, row) in enumerate(group_table.iterrows()):
            cells = []
            if i == 0:
                cells.append(f'<td class="group-cell" rowspan="{row_count}">{escape(str(group))}</td>')
            cells.append(f'<td class="period-cell">{escape(str(period))}</td>')
            cells.extend(f"<td>{escape(str(row[col]))}</td>" for col in columns)
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


@st.cache_data(show_spinner=False)
def cached_compute_baseline(path: str, start_date: str, lookback: int, rebalance: str, rebalance_day: int):
    return compute_baseline(path, start_date, lookback, rebalance, rebalance_day)


@st.cache_data(show_spinner=False)
def cached_compute_baseline_upload(uploaded_file, start_date: str, lookback: int, rebalance: str, rebalance_day: int):
    prices, names = load_baseline_data(uploaded_file)
    return compute_baseline_from_prices(prices, names, start_date, lookback, rebalance, rebalance_day)


@st.cache_data(show_spinner=False)
def cached_load_custom(path_or_file) -> tuple[pd.DataFrame, dict[str, str]]:
    loaded = load_custom_price_data(path_or_file)
    return loaded.prices, loaded.names


st.title("ERC 组合看板")

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
        if baseline_upload is not None:
            data = cached_compute_baseline_upload(baseline_upload, str(start_date), int(lookback), rebalance, int(rebalance_day))
            baseline_source_label = baseline_upload.name
        elif DATA_PATH.exists():
            data = cached_compute_baseline(str(DATA_PATH), str(start_date), int(lookback), rebalance, int(rebalance_day))
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

        tab_overview, tab_data = st.tabs(["表现", "数据"])

        with tab_overview:
            st.plotly_chart(baseline_dashboard_chart(nav_df, data["drawdown_df"], weights, ASSET_LABELS), width="stretch")
            st.subheader("核心指标")
            render_metric_block("收益与风险", metrics, ["年化收益", "年化波动率", "夏普比率", "卡玛比率"])
            render_metric_block("回撤", metrics, ["最大回撤", "最大回撤开始时间", "最大回撤结束时间", "最长回撤修复期(天)"])
            render_metric_block("交易与胜率", metrics, ["月均换手率", "月胜率", "日胜率"])

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
    local_file_path = st.text_input("或输入本地 Excel 文件路径", value="")

    try:
        if uploaded_file is not None:
            custom_prices, custom_names = cached_load_custom(uploaded_file)
            data_label = uploaded_file.name
        elif local_file_path.strip():
            local_path = Path(local_file_path.strip()).expanduser()
            if not local_path.exists():
                st.error(f"找不到文件：{local_path}")
                st.stop()
            custom_prices, custom_names = cached_load_custom(str(local_path))
            data_label = str(local_path)
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
            )
        except Exception as exc:
            st.error(f"自定义组合计算失败：{exc}")
        else:
            selected_labels = {code: custom_names.get(code, code) for code in selected_codes}
            custom_nav = custom_result["nav_df"]
            custom_weights = custom_result["weights"]
            latest_custom_weights = custom_weights.iloc[-1].rename(index=selected_labels)

            c1, c2, c3 = st.columns(3)
            c1.metric("起算日", custom_nav.index.min().strftime("%Y-%m-%d"))
            c2.metric("截止日", custom_nav.index.max().strftime("%Y-%m-%d"))
            c3.metric("组合净值", f"{custom_nav['ERC'].iloc[-1]:.2f}")

            st.caption(
                f"实际计算区间为 {custom_nav.index.min().strftime('%Y-%m-%d')} 至 {custom_nav.index.max().strftime('%Y-%m-%d')}；"
                f"对比基准为 {custom_names.get(benchmark_code, benchmark_code)}。"
            )
            st.plotly_chart(nav_chart(custom_nav), width="stretch")
            st.plotly_chart(drawdown_chart(custom_result["drawdown_df"]), width="stretch")
            st.plotly_chart(weights_chart(custom_weights, selected_labels), width="stretch")

            st.subheader("核心指标")
            render_metric_block("收益与风险", custom_result["metrics"], ["年化收益", "年化波动率", "夏普比率", "卡玛比率"])
            render_metric_block("回撤", custom_result["metrics"], ["最大回撤", "最大回撤开始时间", "最大回撤结束时间", "最长回撤修复期(天)"])
            render_metric_block("交易与胜率", custom_result["metrics"], ["月均换手率", "月胜率", "日胜率"])

            st.subheader("最新一期持仓")
            render_plain_table(
                latest_custom_weights.rename_axis("资产")
                .reset_index(name="最新权重")
                .assign(最新权重=lambda df: df["最新权重"].map(lambda x: f"{x:.2%}"))
            )
