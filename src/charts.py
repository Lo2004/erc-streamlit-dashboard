from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def nav_chart(nav_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    colors = {"ERC": "#111111", "60/40基准": "#767676", "沪深300": "#2f6fbb"}
    for col in nav_df.columns:
        fig.add_trace(
            go.Scatter(
                x=nav_df.index,
                y=nav_df[col],
                name=col,
                mode="lines",
                line=dict(width=2.2, color=colors.get(col)),
            )
        )
    fig.update_layout(
        title="净值表现",
        template="plotly_white",
        height=460,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.update_xaxes(rangeslider_visible=True)
    return fig


def drawdown_chart(drawdown_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    colors = {"ERC": "#9f1d20", "60/40基准": "#767676", "沪深300": "#2f6fbb"}
    for col in drawdown_df.columns:
        fig.add_trace(
            go.Scatter(
                x=drawdown_df.index,
                y=drawdown_df[col],
                name=col,
                mode="lines",
                line=dict(width=2, color=colors.get(col)),
                fill="tozeroy" if col == "ERC" else None,
            )
        )
    fig.update_layout(
        title="动态回撤",
        template="plotly_white",
        height=360,
        hovermode="x unified",
        yaxis_tickformat=".0%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.update_xaxes(rangeslider_visible=True)
    return fig


def weights_chart(weights: pd.DataFrame, labels: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for col in weights.columns:
        fig.add_trace(
            go.Scatter(
                x=weights.index,
                y=weights[col],
                name=labels.get(col, col),
                mode="lines",
                stackgroup="one",
                hovertemplate="%{y:.2%}<extra></extra>",
            )
        )
    fig.update_layout(
        title="动态持仓",
        template="plotly_white",
        height=420,
        hovermode="x unified",
        yaxis_tickformat=".0%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def baseline_dashboard_chart(
    nav_df: pd.DataFrame,
    drawdown_df: pd.DataFrame,
    weights: pd.DataFrame,
    labels: dict[str, str],
) -> go.Figure:
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=("净值表现", "动态回撤", "动态持仓"),
        row_heights=[0.38, 0.28, 0.34],
    )

    nav_colors = {
        "ERC": "#111111",
        "ERC基准": "#767676",
        "ERC+风控增强": "#111111",
        "60/40基准": "#a3a3a3",
        "沪深300": "#2f6fbb",
    }
    dd_colors = {
        "ERC": "#9f1d20",
        "ERC基准": "#767676",
        "ERC+风控增强": "#9f1d20",
        "60/40基准": "#a3a3a3",
        "沪深300": "#2f6fbb",
    }

    for col in nav_df.columns:
        fig.add_trace(
            go.Scatter(
                x=nav_df.index,
                y=nav_df[col],
                name=col,
                mode="lines",
                line=dict(width=2.2, color=nav_colors.get(col)),
                legendgroup=f"nav-{col}",
            ),
            row=1,
            col=1,
        )

    for col in drawdown_df.columns:
        fig.add_trace(
            go.Scatter(
                x=drawdown_df.index,
                y=drawdown_df[col],
                name=f"{col}回撤",
                mode="lines",
                line=dict(width=1.8, color=dd_colors.get(col)),
                fill="tozeroy" if col == "ERC" else None,
                showlegend=False,
            ),
            row=2,
            col=1,
        )

    for col in weights.columns:
        fig.add_trace(
            go.Scatter(
                x=weights.index,
                y=weights[col],
                name=labels.get(col, col),
                mode="lines",
                stackgroup="weights",
                hovertemplate="%{y:.2%}<extra></extra>",
            ),
            row=3,
            col=1,
        )

    fig.update_layout(
        template="plotly_white",
        height=980,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=80, b=20),
    )
    fig.update_yaxes(title_text="净值", row=1, col=1)
    fig.update_yaxes(title_text="回撤", tickformat=".0%", row=2, col=1)
    fig.update_yaxes(title_text="权重", tickformat=".0%", range=[0, 1], row=3, col=1)
    fig.update_xaxes(rangeslider_visible=True, row=3, col=1)
    return fig


def risk_signal_chart(signals: pd.DataFrame, exposure: pd.Series) -> go.Figure:
    plot_df = signals.join(exposure.rename("目标总仓位"), how="left")
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        subplot_titles=("综合风险分数与目标总仓位", "风险因子历史分位", "风险因子原始值"),
        row_heights=[0.34, 0.33, 0.33],
        specs=[[{"secondary_y": True}], [{}], [{"secondary_y": True}]],
    )

    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["risk_score"],
            name="综合风险分数",
            mode="lines",
            line=dict(color="#b42318", width=2.2),
            hovertemplate="%{y:.2%}<extra></extra>",
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["目标总仓位"],
            name="目标总仓位",
            mode="lines",
            line=dict(color="#111111", width=2.0),
            hovertemplate="%{y:.2%}<extra></extra>",
        ),
        row=1,
        col=1,
        secondary_y=True,
    )

    factor_specs = [
        ("q_pc1", "PC1解释度分位", "#8a5cf6"),
        ("q_abs_corr", "平均绝对相关性分位", "#f97316"),
        ("q_vol", "ERC波动率分位", "#0f766e"),
    ]
    for col, name, color in factor_specs:
        fig.add_trace(
            go.Scatter(
                x=plot_df.index,
                y=plot_df[col],
                name=name,
                mode="lines",
                line=dict(color=color, width=1.7),
                hovertemplate="%{y:.2%}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    raw_specs = [
        ("pc1", "PC1解释度", "#8a5cf6", False),
        ("abs_corr", "平均绝对相关性", "#f97316", False),
        ("erc_vol", "ERC年化波动率", "#0f766e", True),
    ]
    for col, name, color, secondary_y in raw_specs:
        fig.add_trace(
            go.Scatter(
                x=plot_df.index,
                y=plot_df[col],
                name=name,
                mode="lines",
                line=dict(color=color, width=1.5),
                hovertemplate="%{y:.2%}<extra></extra>",
                showlegend=True,
            ),
            row=3,
            col=1,
            secondary_y=secondary_y,
        )

    fig.update_layout(
        template="plotly_white",
        height=820,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=80, b=20),
    )
    fig.update_yaxes(title_text="风险分数", tickformat=".0%", range=[0, 1], row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="总仓位", tickformat=".0%", range=[0, 1], row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="历史分位", tickformat=".0%", range=[0, 1], row=2, col=1)
    fig.update_yaxes(title_text="PC1/相关性", tickformat=".0%", row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="波动率", tickformat=".0%", row=3, col=1, secondary_y=True)
    fig.update_xaxes(rangeslider_visible=True, row=3, col=1)
    return fig


def final_signal_chart(signals: pd.DataFrame, exposure: pd.Series) -> go.Figure:
    plot_df = signals.join(exposure.rename("目标总仓位"), how="left")
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        subplot_titles=("Final 指标与均线", "Final 强度与目标总仓位", "构成项：PC1强度与下行半方差"),
        row_heights=[0.33, 0.34, 0.33],
        specs=[[{}], [{"secondary_y": True}], [{"secondary_y": True}]],
    )

    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["final_indicator"],
            name="Final指标",
            mode="lines",
            line=dict(color="#6f42c1", width=1.6),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["final_ma"],
            name="Final_MA252",
            mode="lines",
            line=dict(color="#334155", width=1.4, dash="dash"),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["final_strength"],
            name="Final强度",
            mode="lines",
            line=dict(color="#8c564b", width=1.8),
            hovertemplate="%{y:.2f}<extra></extra>",
        ),
        row=2,
        col=1,
        secondary_y=False,
    )
    for threshold, color, name in [(1.0, "#7f7f7f", "阈值1.0"), (1.2, "#f97316", "阈值1.2"), (1.5, "#dc2626", "阈值1.5")]:
        fig.add_hline(y=threshold, line_dash="dash", line_color=color, line_width=1, row=2, col=1)
        fig.add_trace(
            go.Scatter(x=[None], y=[None], name=name, mode="lines", line=dict(color=color, dash="dash")),
            row=2,
            col=1,
            secondary_y=False,
        )
    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["目标总仓位"],
            name="目标总仓位",
            mode="lines",
            line=dict(color="#111111", width=2.0),
            hovertemplate="%{y:.2%}<extra></extra>",
        ),
        row=2,
        col=1,
        secondary_y=True,
    )

    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["pc1_strength"],
            name="PC1强度(MA30/Mean252)",
            mode="lines",
            line=dict(color="#2f6fbb", width=1.5),
            hovertemplate="%{y:.2f}<extra></extra>",
        ),
        row=3,
        col=1,
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df.index,
            y=plot_df["gm_dsv"],
            name="下行半方差GM63",
            mode="lines",
            line=dict(color="#0f766e", width=1.5),
        ),
        row=3,
        col=1,
        secondary_y=True,
    )

    fig.update_layout(
        template="plotly_white",
        height=820,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=80, b=20),
    )
    fig.update_yaxes(title_text="指标值", row=1, col=1)
    fig.update_yaxes(title_text="强度", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="总仓位", tickformat=".0%", range=[0, 1], row=2, col=1, secondary_y=True)
    fig.update_yaxes(title_text="PC1强度", row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="GM63", row=3, col=1, secondary_y=True)
    fig.update_xaxes(rangeslider_visible=True, row=3, col=1)
    return fig
