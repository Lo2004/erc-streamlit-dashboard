from __future__ import annotations

import itertools

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _style_bottom_rangeslider(fig: go.Figure) -> None:
    fig.update_xaxes(
        rangeslider=dict(
            visible=True,
            thickness=0.035,
            bgcolor="#fbfcfe",
            bordercolor="#d7dde8",
            borderwidth=1,
        ),
        row=3,
        col=1,
    )


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
        vertical_spacing=0.10,
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
        line_color = nav_colors.get(col)
        fig.add_trace(
            go.Scatter(
                x=nav_df.index,
                y=nav_df[col],
                name=col,
                mode="lines",
                line=dict(width=2.2, color=line_color),
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
        height=1000,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=140, b=20),
    )
    fig.update_yaxes(title_text="净值", row=1, col=1)
    fig.update_yaxes(title_text="回撤", tickformat=".0%", row=2, col=1)
    fig.update_yaxes(title_text="权重", tickformat=".0%", range=[0, 1], row=3, col=1)
    _style_bottom_rangeslider(fig)
    return fig


def final_signal_chart(
    signals: pd.DataFrame,
    exposure: pd.Series,
    mid_threshold: float = 1.2,
    high_threshold: float = 1.5,
) -> go.Figure:
    plot_df = signals.join(exposure.rename("目标总仓位"), how="left")
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        subplot_titles=("Final 指标与均线", "Final 强度与目标总仓位", "构成项：PC1强度与下行半方差"),
        row_heights=[0.34, 0.33, 0.33],
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
    threshold_lines = [
        (1.0, "#7f7f7f", "强度1.0"),
        (float(mid_threshold), "#f97316", f"中风险阈值{float(mid_threshold):.2f}"),
        (float(high_threshold), "#dc2626", f"高风险阈值{float(high_threshold):.2f}"),
    ]
    for threshold, color, name in threshold_lines:
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
        height=860,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.11, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=140, b=20),
    )
    fig.update_yaxes(title_text="指标值", row=1, col=1)
    fig.update_yaxes(title_text="强度", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="总仓位", tickformat=".0%", range=[0, 1], row=2, col=1, secondary_y=True)
    fig.update_yaxes(title_text="PC1强度", row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="GM63", row=3, col=1, secondary_y=True)
    _style_bottom_rangeslider(fig)
    return fig


# ── Hierarchical weight chart palettes ──
_GROUP_PALETTES = [
    ["#1a3a5c", "#2e6da4", "#5a9bd5", "#8bbae3"],  # Blues
    ["#7b241c", "#c0392b", "#e0746e", "#edb9b5"],  # Reds
    ["#1a5e32", "#27ae60", "#6fcf97", "#a9dfbf"],  # Greens
    ["#a04000", "#d35400", "#eb984e", "#f0c09a"],  # Oranges
    ["#4a235a", "#7d3c98", "#a569bd", "#cdaedb"],  # Purples
    ["#0e6251", "#17a589", "#48c9b0", "#85e5ce"],  # Teals
    ["#7d6608", "#d4ac0d", "#f1c40f", "#f7dc6f"],  # Yellows
    ["#1b4f72", "#3498db", "#85c1e9", "#bdd7f0"],  # Light blues
]


def hierarchical_weights_chart(
    effective_weights: pd.DataFrame,
    group_assignments: dict[str, list[str]],
    asset_labels: dict[str, str],
) -> go.Figure:
    """
    Stacked-area weight chart where color hue encodes the group and
    shading differentiates assets within the same group.
    """
    fig = go.Figure()

    color_map: dict[str, str] = {}
    for palette_idx, (gname, codes) in enumerate(group_assignments.items()):
        palette = _GROUP_PALETTES[palette_idx % len(_GROUP_PALETTES)]
        codes_present = [c for c in codes if c in effective_weights.columns]
        for j, code in enumerate(codes_present):
            color_map[code] = palette[j % len(palette)]

    for code in effective_weights.columns:
        label = asset_labels.get(code, code)
        gname = _find_group_for_code(code, group_assignments)
        trace_name = f"{gname} > {label}" if gname else label
        fig.add_trace(
            go.Scatter(
                x=effective_weights.index,
                y=effective_weights[code],
                name=trace_name,
                mode="lines",
                stackgroup="one",
                line=dict(width=0.5, color=color_map.get(code, "#777777")),
                hovertemplate="%{y:.2%}<extra>%{fullData.name}</extra>",
            )
        )

    fig.update_layout(
        title="两层 ERC 权重分解",
        template="plotly_white",
        height=420,
        hovermode="x unified",
        yaxis_tickformat=".0%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font_size=11),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def _find_group_for_code(code: str, group_assignments: dict[str, list[str]]) -> str | None:
    for gname, codes in group_assignments.items():
        if code in codes:
            return gname
    return None
