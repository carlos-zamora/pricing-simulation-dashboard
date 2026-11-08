"""Plotly figures. Styling follows the dataviz rules: validated categorical order
(Univ = blue always, Comp = orange always), one axis per chart (small multiples instead of
dual axes), hairline grids, thin marks, legend whenever there are 2+ series.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import SEGMENTS
from .model import (CASE_GAP_ONLY, CASE_LABELS, CUSTOMERS, Bridge, BreakEven, DemandVsUtil,
                    PriceVsUtil, ResearchFit, WhatIfGrid, WhatIfSegment, linfit, whatif_curve)

# Categorical slots, fixed order (validated light/dark set).
BLUE, ORANGE, AQUA, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#e87ba4"
INK = "#898781"                       # muted ink that reads on light and dark surfaces
GRID = "rgba(137,135,129,0.22)"       # hairline grid
UNIV, COMP = BLUE, ORANGE
SEQ_BLUE = [[0, "#cde2fb"], [0.35, "#6da7ec"], [0.7, "#256abf"], [1, "#0d366b"]]


def price(x: float, signed: bool = False) -> str:
    """A per-vehicle price: whole dollars when whole ($41), else cents ($35.50). Signed for deltas
    (+$1, -$1.50). The Univ-Comp gap is always shown as our price minus the competitor's."""
    sign = ("+" if x > 0 else "-" if x < 0 else "") if signed else ""
    x = abs(x) if signed else x
    return f"{sign}${x:,.0f}" if abs(x - round(x)) < 0.005 else f"{sign}${x:,.2f}"


def money(x: float, signed: bool = False) -> str:
    sign = "+" if signed and x > 0 else ""
    if abs(x) >= 1e6:
        return f"{sign}{'-' if x < 0 else ''}${abs(x) / 1e6:,.2f}M"
    if abs(x) >= 1e3:
        return f"{sign}{'-' if x < 0 else ''}${abs(x) / 1e3:,.0f}K"
    return f"{sign}{'-' if x < 0 else ''}${abs(x):,.0f}"


def _style(fig: go.Figure, height: int = 330, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=70, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=INK, size=12),
        showlegend=legend, legend=dict(orientation="h", yanchor="bottom", y=1.13, x=0, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(font_size=12), bargap=0.45,
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=GRID, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor=GRID, linecolor=GRID, zeroline=False, automargin=True)
    return fig


def _line(x, y, name, color, **kw) -> go.Scatter:
    return go.Scatter(x=x, y=y, name=name, mode="lines+markers",
                      line=dict(color=color, width=2),
                      marker=dict(size=8, color=color, line=dict(color="rgba(0,0,0,0)", width=0)),
                      **kw)


# --------------------------------------------------------------------------- #
# Price vs Utilization
# --------------------------------------------------------------------------- #
def price_and_util_by_month(p: PriceVsUtil) -> go.Figure:
    t = p.table
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
                        subplot_titles=("Price ($)", "Utilization"))
    fig.add_trace(_line(t.index, t["univ"], "Univ", UNIV, hovertemplate="%{x}: $%{y:.0f}"), 1, 1)
    fig.add_trace(_line(t.index, t["comp"], "Comp", COMP, hovertemplate="%{x}: $%{y:.0f}"), 1, 1)
    fig.add_trace(_line(t.index, t["util"], "Utilization", AQUA,
                        hovertemplate="%{x}: %{y:.0%}", showlegend=False), 2, 1)
    fig.update_yaxes(tickprefix="$", row=1, col=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.05], row=2, col=1)
    fig.update_annotations(font=dict(size=12, color=INK))
    return _style(fig, 430)


def scatter_with_fit(x, y, labels, xtitle: str, ytitle: str, ytick: str = ".0%",
                     slope_scale: float = 100.0, slope_unit: str = "pts per +$1",
                     color: str = BLUE, xtick: str | None = None,
                     center_x_zero: bool = False) -> go.Figure:
    """Scatter of months plus a least-squares line. The legend states the slope (converted
    with ``slope_scale`` into ``slope_unit``) and R², one fact per line."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="markers+text", text=list(labels),
                             textposition="top center", textfont=dict(color=INK, size=11),
                             marker=dict(size=11, color=color, line=dict(color="rgba(255,255,255,.9)", width=2)),
                             name="Month", cliponaxis=False,
                             hovertemplate="%{text}<br>x=%{x:,.2f}<br>y=%{y:.3f}<extra></extra>"))
    fit = linfit(x, y)
    if fit.slope is not None:
        slope = fit.slope * slope_scale
        r2 = "n/a" if fit.r2 is None else f"{fit.r2:.2f}"
        xs = np.array([x.min(), x.max()])
        fig.add_trace(go.Scatter(
            x=xs, y=fit.predict(xs), mode="lines", line=dict(color=INK, width=2),
            name=f"Best fit<br>slope {slope:+.2f} {slope_unit}<br>R² {r2}",
            hovertemplate=f"Best fit: slope {slope:+.2f} {slope_unit}<extra></extra>"))
    else:
        # Keep the legend honest when no line can be drawn.
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", line=dict(color=INK, width=2),
                                 name="Best fit<br>n/a (x never changed)"))
    fig.update_xaxes(title=xtitle, tickformat=xtick)
    if center_x_zero:
        # Same x scale and 0 in the middle on every gap chart, so charts compare at a glance.
        half = (float(np.nanmax(np.abs(x))) if x.size else 0.0) * 1.2 or 1.0
        fig.update_xaxes(range=[-half, half], zeroline=True, zerolinecolor=INK, zerolinewidth=1)
    fig.update_yaxes(title=ytitle, tickformat=ytick)
    span = float(np.ptp(y)) or abs(float(y.mean())) * 0.1 or 1.0
    fig.update_yaxes(range=[float(y.min()) - 0.15 * span, float(y.max()) + 0.25 * span])
    fig = _style(fig, 430, legend=True)
    # Legend below the plot so multi-line entries are never cut off in narrow columns.
    fig.update_layout(margin=dict(t=20, b=8),
                      legend=dict(orientation="v", xanchor="left", x=0, yanchor="top", y=-0.34))
    return fig


def util_vs_gap(p: PriceVsUtil) -> go.Figure:
    t = p.table
    return scatter_with_fit(t["gap"], t["util"], t.index, "Univ – Comp price gap ($)",
                            "Utilization", slope_scale=100, slope_unit="util pts per +$1 gap",
                            center_x_zero=True)


# --------------------------------------------------------------------------- #
# Demand vs Util
# --------------------------------------------------------------------------- #
def util_vs_demand(d: DemandVsUtil) -> go.Figure:
    t = d.table
    return scatter_with_fit(t["demand"], t["util"], t.index, "Demand (orders)", "Utilization",
                            slope_scale=10000 * 100, slope_unit="util pts per 10K orders",
                            xtick=",.0f")


def price_effect_after_demand(d: DemandVsUtil) -> go.Figure:
    t = d.table
    labels = [f"{m} ({price(g, True)})" for m, g in zip(t.index, t["gap"])]
    return scatter_with_fit(t["gap"], t["residual"] * 100, labels, "Univ – Comp price gap ($)",
                            "Utilization vs demand trend (pts)", ytick=".1f",
                            slope_scale=1, slope_unit="util pts per +$1 gap", color=ORANGE,
                            center_x_zero=True)


def indexed_trends(d: DemandVsUtil) -> go.Figure:
    t = d.table
    fig = go.Figure()
    for col, name, color in (("idx_demand", "Demand", AQUA), ("idx_univ", "Univ price", UNIV),
                             ("idx_comp", "Comp price", ORANGE), ("idx_util", "Utilization", MAGENTA)):
        fig.add_trace(_line(t.index, t[col], name, color, hovertemplate="%{x}: %{y:.1f}"))
    fig.update_yaxes(title=f"Index ({t.index[0]} = 100)")
    return _style(fig, 430)


def sales_vs_unfilled(months, sales, unfilled, util) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
                        subplot_titles=("Miami orders", "Univ utilization (weekday)"))
    fig.add_trace(go.Bar(x=months, y=sales, name="Total sales", marker_color=BLUE,
                         marker_line=dict(color="rgba(0,0,0,0)", width=0),
                         hovertemplate="%{x}: %{y:,.0f}"), 1, 1)
    fig.add_trace(go.Bar(x=months, y=unfilled, name="Unfilled orders", marker_color=ORANGE,
                         hovertemplate="%{x}: %{y:,.0f}"), 1, 1)
    fig.add_trace(_line(months, util, "Utilization", AQUA, showlegend=False,
                        hovertemplate="%{x}: %{y:.0%}"), 2, 1)
    fig.update_layout(barmode="stack")
    fig.update_yaxes(tickformat=".0%", range=[0, 1.05], row=2, col=1)
    fig.update_annotations(font=dict(size=12, color=INK))
    return _style(fig, 420)


# --------------------------------------------------------------------------- #
# Business vs leisure (market research)
# --------------------------------------------------------------------------- #
_CUSTOMER_STYLE = {"business": ("Business", BLUE, "top center"),
                   "leisure": ("Leisure", ORANGE, "bottom center")}


def research_scatter(f: ResearchFit) -> go.Figure:
    """Univ share among business and leisure customers vs the price gap, each with a best-fit
    line whose slope and R² are in the legend. No line where the segment can't be measured."""
    t = f.table.dropna(subset=["business", "leisure"])
    fig = go.Figure()
    for cust in CUSTOMERS:
        name, color, pos = _CUSTOMER_STYLE[cust]
        x, y = t["gap"].to_numpy(float), t[cust].to_numpy(float)
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="markers+text", text=list(t.index), textposition=pos,
            textfont=dict(color=INK, size=10), cliponaxis=False, name=name,
            marker=dict(size=10, color=color, line=dict(color="rgba(255,255,255,.9)", width=2)),
            hovertemplate=f"{name} %{{text}}<br>gap %{{x:+.0f}}<br>share %{{y:.0%}}<extra></extra>"))
        fit = linfit(x, y)
        if f.measurable and fit.slope is not None:
            xs = np.array([x.min(), x.max()])
            r2 = "n/a" if fit.r2 is None else f"{fit.r2:.2f}"
            fig.add_trace(go.Scatter(
                x=xs, y=fit.predict(xs), mode="lines", line=dict(color=color, width=2),
                name=f"{name} best fit<br>slope {fit.slope * 100:+.2f} share pts per +$1<br>R² {r2}",
                hovertemplate=f"{name}: {fit.slope * 100:+.2f} share pts per +$1<extra></extra>"))
    if not f.measurable:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", line=dict(color=INK, width=2),
                                 name="No best fit (can't be measured)"))
    half = (float(np.nanmax(np.abs(t["gap"]))) if len(t) else 0.0) * 1.3 or 1.0
    fig.update_xaxes(title="Univ – Comp price gap ($)", range=[-half, half], zeroline=True,
                     zerolinecolor=INK, zerolinewidth=1)
    ys = pd.concat([t["business"], t["leisure"]]) if len(t) else pd.Series([0.5])
    span = max(float(ys.max() - ys.min()), 0.02)
    # Research shares are whole percentages: one tick per point, never repeated labels.
    fig.update_yaxes(title="Univ share of customers", tickformat=".0%", dtick=0.01,
                     range=[float(ys.min()) - 0.3 * span, float(ys.max()) + 0.3 * span])
    fig = _style(fig, 430)
    fig.update_layout(margin=dict(t=20, b=8),
                      legend=dict(orientation="v", xanchor="left", x=0, yanchor="top", y=-0.3))
    return fig


def research_shares_by_month(f: ResearchFit) -> go.Figure:
    """Business and leisure share by month, plus Univ's overall share from unit sales as a check
    on the survey."""
    t = f.table
    fig = go.Figure()
    for cust in CUSTOMERS:
        name, color, _ = _CUSTOMER_STYLE[cust]
        fig.add_trace(_line(t.index, t[cust], f"{name} (research)", color,
                            hovertemplate="%{x}: %{y:.0%}"))
    fig.add_trace(go.Scatter(x=t.index, y=t["overall"], name="All customers (unit sales)",
                             mode="lines+markers", line=dict(color=AQUA, width=2, dash="dot"),
                             marker=dict(size=6, color=AQUA), hovertemplate="%{x}: %{y:.1%}"))
    fig.update_yaxes(title="Univ share", tickformat=".0%", dtick=0.01)
    fig = _style(fig, 430)
    fig.update_layout(margin=dict(t=20, b=8),
                      legend=dict(orientation="v", xanchor="left", x=0, yanchor="top", y=-0.18))
    return fig


# --------------------------------------------------------------------------- #
# Profit
# --------------------------------------------------------------------------- #
def price_and_profit(df: pd.DataFrame, dayparts=("Weekday", "Weekend"),
                     profit_label: str = "Pre-tax profit") -> go.Figure:
    """One city, panels stacked so every month lines up vertically: a price panel per day period
    (Univ vs Comp), utilization, profit, then a short strip for unfilled orders and fleet size.
    Competitor utilization is not reported, so it is not shown."""
    dayparts = list(dayparts)
    has_strip = "Unfilled orders" in df and "Fleet size" in df
    titles = ([f"{dp} price ($)" for dp in dayparts] + ["Utilization (Univ)", profit_label]
              + (["Unfilled orders", "Fleet size (vehicles)"] if has_strip else []))
    heights = [190] * (len(dayparts) + 2) + ([120, 120] if has_strip else [])
    total = sum(heights)
    fig = make_subplots(rows=len(titles), cols=1, shared_xaxes=True, subplot_titles=titles,
                        row_heights=[h / total for h in heights], vertical_spacing=0.035)
    for i, dp in enumerate(dayparts):
        r = i + 1
        fig.add_trace(_line(df.index, df[f"{dp} price"], "Univ", UNIV, legendgroup="Univ",
                            showlegend=(i == 0), hovertemplate="%{x}: $%{y:.2f}"), r, 1)
        fig.add_trace(_line(df.index, df[f"{dp} comp price"], "Comp", COMP, legendgroup="Comp",
                            showlegend=(i == 0), hovertemplate="%{x}: $%{y:.2f}"), r, 1)
        fig.update_yaxes(tickprefix="$", row=r, col=1)
    r = len(dayparts) + 1
    for dp, color in zip(dayparts, (AQUA, MAGENTA)):
        fig.add_trace(_line(df.index, df[f"{dp} utilization"], dp, color,
                            hovertemplate="%{x}: %{y:.0%}"), r, 1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.05], row=r, col=1)
    r += 1
    fig.add_trace(go.Bar(x=df.index, y=df["Pre-tax profit"], marker_color=BLUE, showlegend=False,
                         customdata=[money(v) for v in df["Pre-tax profit"]],
                         hovertemplate="%{x}: %{customdata}<extra></extra>"), r, 1)
    fig.update_yaxes(tickformat="$~s", row=r, col=1)
    if has_strip:
        r += 1
        fig.add_trace(go.Bar(x=df.index, y=df["Unfilled orders"], marker_color=ORANGE, showlegend=False,
                             customdata=df["Unfilled share"],
                             hovertemplate="%{x}: %{y:,.0f} unfilled (%{customdata:.1%} of demand)"
                                           "<extra></extra>"), r, 1)
        fig.update_yaxes(tickformat="~s", autorange="reversed", rangemode="tozero", row=r, col=1)
        r += 1
        fig.add_trace(_line(df.index, df["Fleet size"], "Fleet", AQUA, showlegend=False,
                            hovertemplate="%{x}: %{y:,.0f} vehicles"), r, 1)
        fig.update_yaxes(tickformat="~s", row=r, col=1)
    fig.update_annotations(font=dict(size=12, color=INK))
    fig = _style(fig, total + 90)
    fig.update_layout(margin=dict(t=50), legend=dict(y=1.0, yanchor="bottom"))
    return fig


def scope_profit_chart(df: pd.DataFrame, label: str) -> go.Figure:
    """Profit by month: one stacked bar segment per city, with the Florida total marked on top."""
    fig = go.Figure()
    cities = [c for c in df.columns if c != "Florida"]
    for city, color in zip(cities, (BLUE, ORANGE)):
        fig.add_trace(go.Bar(x=df.index, y=df[city], name=city, marker_color=color,
                             customdata=[money(v) for v in df[city]],
                             hovertemplate="%{x}: %{customdata}<extra>" + city + "</extra>"))
    if "Florida" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Florida"], name="Florida total", mode="markers+text",
            text=[money(v) for v in df["Florida"]], textposition="top center",
            textfont=dict(color=INK, size=11), marker=dict(size=9, color=INK),
            cliponaxis=False, hovertemplate="%{x}: %{text}<extra>Florida total</extra>"))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(tickformat="$~s", title=label)
    return _style(fig, 340)


def bridge_chart(b: Bridge) -> go.Figure:
    labels = [l for l, _ in b.steps]
    values = [v for _, v in b.steps]
    measure = ["absolute"] + ["relative"] * (len(values) - 2) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=measure,
        text=[money(v, signed=0 < i < len(values) - 1) for i, v in enumerate(values)],
        textposition="outside", textfont=dict(color=INK),
        increasing=dict(marker=dict(color=BLUE)), decreasing=dict(marker=dict(color=ORANGE)),
        totals=dict(marker=dict(color=INK)),
        connector=dict(line=dict(color=GRID, width=1)),
        hovertemplate="%{x}: %{text}<extra></extra>"))
    fig.update_yaxes(tickformat="$~s")
    _style(fig, 300, legend=False)
    fig.update_layout(margin=dict(t=24))       # no legend or subplot titles: no room needed above
    return fig


def whatif_lines(segs_by_case: dict[str, dict[tuple[str, str], WhatIfSegment]],
                 segments: list[tuple[str, str]] | None = None) -> dict[tuple[str, str], go.Figure]:
    """One figure per segment (city, day period): change in profit vs actual as that segment's
    price moves, one line per sensitivity assumption. The other prices stay put."""
    first_case = next(iter(segs_by_case.values()))
    keys = list(segments) if segments else list(first_case)
    colors = {case: c for case, c in zip(segs_by_case, (BLUE, AQUA))}
    figs = {}
    for key in keys:
        fig = go.Figure()
        measurable = segs_by_case[CASE_GAP_ONLY][key].slope_used < 0
        p0 = first_case[key].price0
        if measurable:
            for case, segs in segs_by_case.items():
                cv = whatif_curve(segs[key])
                fig.add_trace(go.Scatter(
                    x=cv["price"], y=cv["delta_profit"], mode="lines+markers",
                    line=dict(color=colors[case], width=2), marker=dict(size=8, color=colors[case]),
                    name=CASE_LABELS[case],
                    customdata=np.c_[cv["utilization"], cv["rentals"]],
                    hovertemplate="Price $%{x:.0f}<br>Δ profit %{y:$,.0f}<br>"
                                  "Util %{customdata[0]:.0%}<br>Rentals %{customdata[1]:,.0f}"
                                  f"<extra>{CASE_LABELS[case]}</extra>"))
        else:
            fig.add_annotation(text="Price sensitivity can't be measured<br>yet, so no curve is drawn",
                               xref="paper", yref="paper", x=0.5, y=0.75, showarrow=False,
                               font=dict(size=12, color=INK))
            fig.update_yaxes(range=[-1, 1], showticklabels=False)
            fig.update_xaxes(range=[p0 - 3, p0 + 3], tickvals=[p0], ticktext=[f"${p0:.0f}"])
        fig.add_trace(go.Scatter(x=[p0], y=[0], mode="markers", name="Actual price",
                                 marker=dict(size=12, color=ORANGE, line=dict(color="white", width=2)),
                                 hoverinfo="skip"))
        fig.add_hline(y=0, line=dict(color=INK, width=1))
        fig.update_xaxes(tickprefix="$" if measurable else "")
        if measurable:
            fig.update_yaxes(tickformat="$~s", title_text="Δ profit vs actual")
        _style(fig, 330)
        fig.update_layout(margin=dict(t=50))
        figs[key] = fig
    return figs


def whatif_heatmap(g: WhatIfGrid) -> go.Figure:
    z = g.profit.values
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"${p:.0f}" for p in g.weekend_prices], y=[f"${p:.0f}" for p in g.weekday_prices],
        colorscale=SEQ_BLUE, text=[["" if np.isnan(v) else money(v) for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(size=10), xgap=2, ygap=2,
        colorbar=dict(title="Profit", tickformat="$~s"),
        hovertemplate="Weekday %{y} · Weekend %{x}<br>%{text}<extra></extra>"))
    # Mark the actual and the best cells with outlines.
    def cell(wd, we, color, name):
        i, j = g.weekday_prices.index(wd), g.weekend_prices.index(we)
        fig.add_shape(type="rect", x0=j - .5, x1=j + .5, y0=i - .5, y1=i + .5,
                      line=dict(color=color, width=3))
        fig.add_annotation(x=j, y=i - 0.36, text=name, showarrow=False,
                           font=dict(size=9, color=color), bgcolor="rgba(255,255,255,.75)")
    mid = g.deltas.index(0)
    cell(g.weekday_prices[mid], g.weekend_prices[mid], ORANGE, "actual")
    if (g.best_weekday, g.best_weekend) != (g.weekday_prices[mid], g.weekend_prices[mid]):
        cell(g.best_weekday, g.best_weekend, "#0b0b0b", "best")
    fig.update_xaxes(title="Weekend price", type="category")
    fig.update_yaxes(title="Weekday price", type="category", autorange="reversed")
    return _style(fig, 420, legend=False)


def break_even_chart(be: BreakEven) -> go.Figure:
    curve = be.curve(np.linspace(0.4, 1.0, 25))
    fig = go.Figure()
    for color, label in zip((BLUE, ORANGE), curve.columns):
        fig.add_trace(go.Scatter(x=curve.index, y=curve[label], mode="lines", name=label,
                                 line=dict(color=color, width=2),
                                 hovertemplate="Util %{x:.0%}: %{y:$,.0f}<extra>" + label + "</extra>"))
        x0 = be.break_even[label]
        fig.add_trace(go.Scatter(x=[x0], y=[0], mode="markers", showlegend=False,
                                 marker=dict(size=10, color=color, line=dict(color="white", width=2)),
                                 hovertemplate=f"Break-even {x0:.1%}<extra>{label}</extra>"))
    fig.add_vline(x=be.actual_util, line=dict(color=INK, width=1.5),
                  annotation_text=f"actual {be.actual_util:.0%}", annotation_font_color=INK)
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    fig.update_xaxes(tickformat=".0%", title="Blended utilization")
    fig.update_yaxes(tickformat="$~s", title="Pre-tax profit")
    return _style(fig, 330)


def unit_economics_chart(ue: pd.DataFrame, city: str) -> go.Figure:
    d = ue[ue["city"] == city]
    fig = go.Figure()
    for col, color in (("Variable cost", BLUE), ("Vehicle inventory cost", ORANGE),
                       ("Other fixed cost", AQUA), ("Pre-tax profit", MAGENTA)):
        fig.add_trace(go.Bar(x=d["month"], y=d[col], name=col, marker_color=color,
                             hovertemplate="%{x}: $%{y:,.0f}<extra>" + col + "</extra>"))
    fig.update_layout(barmode="relative")
    fig.update_yaxes(tickprefix="$", title="Revenue per vehicle per month")
    return _style(fig, 320)


def contribution_chart(c: pd.DataFrame, city: str) -> go.Figure:
    d = c[c["city"] == city]
    fig = go.Figure()
    for col, color in (("Weekday contribution", BLUE), ("Weekend contribution", AQUA)):
        fig.add_trace(go.Bar(x=d["month"], y=d[col], name=col.split()[0], marker_color=color,
                             hovertemplate="%{x}: %{y:$,.0f}<extra>" + col + "</extra>"))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(tickformat="$~s")
    return _style(fig, 320)
