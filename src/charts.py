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
