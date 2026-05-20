from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


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
