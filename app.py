"""Pricing Simulation Dashboard.   Run:  streamlit run app.py"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from pricing import charts, insights, model
from pricing.config import ALL_TABLES, CITIES, DAYPARTS, REQUIRED_TABLES, SEGMENTS
from pricing.data import SimData
from pricing.parsers import ParseError, detect_kind, guess_city_from_name, parse_text, read_grid
from pricing.store import ImportReport, Store

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "facts.csv"
SAMPLE_DIR = ROOT / "sample_data"

st.set_page_config(page_title="Pricing Simulation Dashboard", page_icon="📊", layout="wide")


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def get_store() -> Store:
    if "store" not in st.session_state:
        store = Store(DATA_FILE)
        if store.facts.empty and SAMPLE_DIR.exists():
            store.add_folder(SAMPLE_DIR)       # first run: start from the bundled sample
            store.save()
            st.session_state["first_run"] = True
        st.session_state["store"] = store
    return st.session_state["store"]


def show_report(rep: ImportReport) -> None:
    for line in rep.imported:
        st.success(line)
    for e in rep.errors:
        st.error(e)
    for w in rep.warnings:
        st.warning(w)
    if rep.months_added:
        st.info(f"New months added: {', '.join(rep.months_added)}")
    if rep.changed:
        with st.expander(f"⚠️ {len(rep.changed)} previously imported values changed"):
            st.write("\n".join(f"- {c}" for c in rep.changed[:200]))


def finish_import(rep: ImportReport) -> None:
    """Save, remember the report across the rerun, and refresh every tab."""
    if not rep.errors or rep.imported:
        store.save()
    st.session_state["last_report"] = rep
    st.rerun()


store = get_store()


# --------------------------------------------------------------------------- #
# Data tab (defined first so an empty dataset can still import)
# --------------------------------------------------------------------------- #
def data_tab() -> None:
    if "last_report" in st.session_state:
        show_report(st.session_state.pop("last_report"))
    st.subheader("Import a new month")
    st.caption("Copy each table from the simulation and paste it here, drop the saved .txt files, "
               "or import a whole folder. Re-importing the same months is safe: values are "
               "merged by month, and any change to earlier months is flagged.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Paste one table**")
        text = st.text_area("Paste copied table (tab-separated)", height=170, key="paste_text",
                            label_visibility="collapsed",
                            placeholder="Copy a table from the simulation and paste it here…")
        city = None
        if text.strip():
            try:
                kind = detect_kind(read_grid(text))
                st.caption(f"Detected: **{ALL_TABLES.get(kind, 'net income screen') if kind != 'net_income' else 'Net income screen'}**")
                if kind == "net_income":
                    city = st.selectbox("Which city is this net income screen for?", CITIES,
                                        index=None, placeholder="Choose a city")
            except ParseError as exc:
                st.error(str(exc))
        if st.button("Add pasted table", disabled=not text.strip()):
            finish_import(store.add_text(text, city=city, label="Pasted table"))

    with c2:
        st.markdown("**Drop files or import a folder**")
        files = st.file_uploader("Upload .txt tables", type=["txt"], accept_multiple_files=True,
                                 label_visibility="collapsed")
        if files and st.button(f"Import {len(files)} file(s)"):
            rep = ImportReport()
            for f in files:
                store.add_text(f.getvalue().decode("utf-8-sig"),
                               city=guess_city_from_name(f.name), label=f.name, report=rep)
            finish_import(rep)
        folder = st.text_input("Folder of .txt files", value=str(ROOT / "inbox"),
                               help="Net income files need 'orlando' or 'miami' in the file name.")
        if st.button("Import folder"):
            finish_import(store.add_folder(folder))

    st.divider()
    st.subheader("What's in the dataset")
    cov = store.coverage()
    if cov.empty:
        st.info("No data yet. Import the tables above, or load the bundled sample.")
    else:
        complete = store.complete_months()
        st.write(f"Complete months (usable for analysis): **{', '.join(complete) or 'none'}**")
        st.caption("Values held per month and table (0 = missing). A month needs all required "
                   "tables to appear in the analysis; net income needs both cities.")
        st.dataframe(cov.T, width="stretch")
        with st.expander("Tidy data (every value, one row each)"):
            st.dataframe(store.facts, width="stretch", hide_index=True)
            st.download_button("Download CSV", store.facts.to_csv(index=False), "facts.csv")
    c3, c4 = st.columns(2)
    if c3.button("Load bundled sample data"):
        store.clear()
        store.add_folder(SAMPLE_DIR)
        store.save()
        st.rerun()
    if c4.button("Clear all data"):
        store.clear()
        store.save()
        st.rerun()


# --------------------------------------------------------------------------- #
# Analysis context
# --------------------------------------------------------------------------- #
st.title("Pricing Simulation Dashboard")
months_ok = store.complete_months()
if len(months_ok) < 2:
    st.warning("Need at least 2 complete months to analyse. Import data below.")
    data_tab()
    st.stop()

data = SimData(store.facts, months_ok)

with st.sidebar:
    st.header("Controls")
    base = st.selectbox("Base month", data.months, index=0,
                        help="Start of the profit bridge; 'old prices' in break-even.")
    focus = st.selectbox("Focus month", data.months, index=len(data.months) - 1,
                         help="Month the what-if and break-even are built on.")
    case = st.radio("Price-sensitivity case", model.CASES,
                    help="Gap-only: slope from Univ–Comp price gap alone (upper bound on price "
                         "sensitivity). Demand-adjusted: slope left after removing demand "
                         "(lower bound).")
    st.caption(f"Months analysed: {', '.join(data.months)}")
    incomplete = [m for m in store.months() if m not in months_ok]
    if incomplete:
        st.warning(f"Incomplete (skipped): {', '.join(incomplete)}. See Import & data.")

if base == focus:
    st.warning("Base and focus month are the same: pick two different months for the bridge.")

pvu = model.price_vs_util(data)
dvu = model.demand_vs_util(data)
segs = model.whatif_segments(data, focus, case, pvu, dvu)
bridges = {c: model.profit_bridge(data, c, base, focus) for c in CITIES}
bes = {c: model.break_even(data, c, focus, base) for c in CITIES}
grids = {c: model.whatif_grid(data, c, focus, segs) for c in CITIES}
ue = model.unit_economics(data)
contrib = model.weekday_weekend_contribution(data)
dem_readouts = insights.demand_readouts(data, dvu)   # also populates demand_estimated
for note in insights.caveats(data):
    st.caption(f"ℹ️ {note}")

tabs = st.tabs(["Overview", "Price vs Utilization", "Demand vs Utilization", "Profit bridge",
                "What-if & planner", "Break-even & economics", "Import & data"])

# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #
with tabs[0]:
    prev = data.months[data.months.index(focus) - 1] if data.months.index(focus) > 0 else None
    cols = st.columns(len(CITIES))
    for col, city in zip(cols, CITIES):
        with col:
            st.subheader(city)
            profit = data.net("total", city, "Pre-Tax Profit")
            m1, m2, m3 = st.columns(3)
            m1.metric(f"{focus} pre-tax profit", charts.money(profit[focus]),
                      charts.money(profit[focus] - profit[prev], True) if prev else None)
            m2.metric("Weekday util", f"{data.utilization(city, 'Weekday')[focus]:.0%}")
            m3.metric("Weekend util", f"{data.utilization(city, 'Weekend')[focus]:.0%}")
            st.plotly_chart(charts.price_and_profit(model.price_vs_profit(data, city)),
                            width="stretch", key=f"ov_{city}")
    st.subheader("Key readouts")
    lines = [insights.bridge_readout(bridges[c]) for c in CITIES]
    lines += [insights.break_even_readout(bes[c]) for c in CITIES]
    lines += [x for c in CITIES if (x := insights.weekend_readout(data, c, focus))]
    lines += [insights.whatif_readout(grids[c]) + f" ({case.split(' (')[0].lower()} case)"
              for c in CITIES]
    st.markdown("\n".join(f"- {l}" for l in lines))

# --------------------------------------------------------------------------- #
# Price vs Utilization
# --------------------------------------------------------------------------- #
with tabs[1]:
    st.caption("Slope = utilization points per +$1 of Univ–Comp price gap (negative means being "
               "pricier costs utilization). R² = share of utilization swings the gap alone "
               "explains. Demand moves at the same time, so see the next tab before concluding.")
    ro = insights.price_readouts(pvu)
    for seg in SEGMENTS:
        p = pvu[seg]
        st.markdown(f"#### {p.name}")
        a, b = st.columns(2)
        a.plotly_chart(charts.price_and_util_by_month(p), width="stretch", key=f"pu1_{seg}")
        b.plotly_chart(charts.util_vs_gap(p), width="stretch", key=f"pu2_{seg}")
        s = "n/a" if p.slope_pts is None else f"{p.slope_pts:+.1f} pts per $1"
        r = "n/a" if p.r2 is None else f"{p.r2:.2f}"
        st.caption(f"Gap slope **{s}** · R² **{r}** — {ro[seg]}")

# --------------------------------------------------------------------------- #
# Demand vs Utilization
# --------------------------------------------------------------------------- #
with tabs[2]:
    st.caption("Utilization regressed on demand; the leftover is what price (the Univ–Comp gap) "
               "might explain. The 'price slope' is the effect of price after demand is "
               "removed.")
    for seg in SEGMENTS:
        d = dvu[seg]
        st.markdown(f"#### {d.name}")
        a, b, c = st.columns(3)
        a.plotly_chart(charts.util_vs_demand(d), width="stretch", key=f"dv1_{seg}")
        b.plotly_chart(charts.price_effect_after_demand(d), width="stretch", key=f"dv2_{seg}")
        c.plotly_chart(charts.indexed_trends(d), width="stretch", key=f"dv3_{seg}")
        r2 = "n/a" if d.r2_demand is None else f"{d.r2_demand:.2f}"
        ds = "n/a" if d.demand_slope_pts_per_10k is None else f"{d.demand_slope_pts_per_10k:+.1f}"
        ps = "n/a" if d.price_slope_pts is None else f"{d.price_slope_pts:+.1f}"
        st.caption(f"R² vs demand **{r2}** · demand slope **{ds}** pts per 10K orders · "
                   f"price slope **{ps}** pts per $1 — {dem_readouts[seg]}")
    st.markdown("#### Miami: sales vs unfilled orders")
    st.plotly_chart(charts.sales_vs_unfilled(
        data.months, data.market("Miami", "sales"), data.market("Miami", "unfilled"),
        data.utilization("Miami", "Weekday")), width="stretch", key="miami_unfilled")

# --------------------------------------------------------------------------- #
# Profit bridge
# --------------------------------------------------------------------------- #
with tabs[3]:
    st.caption("Price effect = price change × new volume. Volume effect = volume change × old "
               "contribution per rental. Variable-cost and fixed-cost steps are straight "
               "differences; any remainder is rounding in the simulation's reported numbers.")
    cols = st.columns(len(CITIES))
    for col, city in zip(cols, CITIES):
        with col:
            st.subheader(city)
            st.plotly_chart(charts.bridge_chart(bridges[city]), width="stretch", key=f"br_{city}")
            st.caption(insights.bridge_readout(bridges[city]))

# --------------------------------------------------------------------------- #
# What-if & planner
# --------------------------------------------------------------------------- #
with tabs[4]:
    st.subheader(f"Price planner (built on {focus} actuals)")
    st.caption(f"Enter candidate Univ prices. Projection uses the **{case}** case: utilization "
               "changes by the case's slope per $1 of price change (never rises with price), "
               "volume scales with utilization, and the variable cost per rental is held.")
    prices: dict[tuple[str, str], float] = {}
    cols = st.columns(4)
    for col, seg in zip(cols, SEGMENTS):
        s = segs[seg]
        comp = data.price(seg[0], seg[1], "Comp")[focus]
        prices[seg] = col.number_input(
            f"{s.name} ($)", value=float(s.price0), step=1.0, min_value=1.0,
            key=f"plan_{focus}_{seg}", help=f"{focus} actual ${s.price0:.0f}; Comp ${comp:.0f}")
        col.caption(f"actual ${s.price0:.0f} · Comp ${comp:.0f} · util {s.util0:.0%}")
    scen = model.scenario_profit(data, focus, segs, prices)
    cols = st.columns(len(CITIES))
    for col, city in zip(cols, CITIES):
        with col:
            r = scen[city]
            diff = r["profit"] - r["actual"]
            col.metric(f"{city} projected pre-tax profit", charts.money(r["profit"]),
                       charts.money(diff, True) + f" vs {focus} actual",
                       delta_color="off" if abs(diff) < 1 else "normal")
            rows = [{"Segment": dp, "Projected utilization": f"{v['utilization']:.0%}",
                     "Projected rentals": f"{v['rentals']:,.0f}",
                     "Δ profit": charts.money(v["delta"], True)}
                    for dp, v in r["detail"].items()]
            col.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.divider()

    st.subheader("Profit by price: one segment at a time")
    st.caption("Orange dot = actual price. Each curve changes only that segment's price.")
    st.plotly_chart(charts.whatif_lines(segs), width="stretch", key="wi_lines")

    st.subheader("Profit grid: weekday × weekend price")
    st.caption("Centre cell = actual prices. Outlines mark actual (orange) and best-in-grid "
               "(black).")
    cols = st.columns(len(CITIES))
    for col, city in zip(cols, CITIES):
        with col:
            st.markdown(f"**{city}**")
            st.plotly_chart(charts.whatif_heatmap(grids[city]), width="stretch", key=f"wi_h_{city}")
            st.caption(insights.whatif_readout(grids[city]))
    st.caption("Slopes used (util pts per $1, capped at 0): " + " · ".join(
        f"{s.name} {s.slope_used:+.1f}" for s in segs.values()))

# --------------------------------------------------------------------------- #
# Break-even & economics
# --------------------------------------------------------------------------- #
with tabs[5]:
    st.subheader(f"Break-even utilization ({focus} volumes & costs)")
    cols = st.columns(len(CITIES))
    for col, city in zip(cols, CITIES):
        with col:
            st.markdown(f"**{city}**")
            st.plotly_chart(charts.break_even_chart(bes[city]), width="stretch", key=f"be_{city}")
            st.caption(insights.break_even_readout(bes[city]))
    st.subheader("Revenue per vehicle per month: where it goes")
    cols = st.columns(len(CITIES))
    for col, city in zip(cols, CITIES):
        col.markdown(f"**{city}**")
        col.plotly_chart(charts.unit_economics_chart(ue, city), width="stretch", key=f"ue_{city}")
    st.subheader("Weekday vs weekend profit contribution")
    cols = st.columns(len(CITIES))
    for col, city in zip(cols, CITIES):
        col.markdown(f"**{city}**")
        col.plotly_chart(charts.contribution_chart(contrib, city), width="stretch", key=f"ct_{city}")
    with st.expander("Tables"):
        st.dataframe(ue, hide_index=True, width="stretch")
        st.dataframe(contrib, hide_index=True, width="stretch")

with tabs[6]:
    data_tab()
