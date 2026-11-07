"""Pricing Simulation Dashboard.   Run:  streamlit run app.py"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from pricing import charts, insights, model
from pricing.config import (ALL_TABLES, CITIES, CITY_OPTIONS, DAYPART_OPTIONS, DAYPARTS,
                            REQUIRED_TABLES, SEGMENTS, scope)
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


def bullets(items) -> str:
    """Markdown bullet list: one finding per line."""
    return "\n".join(f"- {i}" for i in items)


def nested(lines: list[str]) -> str:
    """First line as a bullet, the rest as sub-bullets beneath it."""
    return "\n".join([f"- {lines[0]}", *(f"    - {l}" for l in lines[1:])])


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
    st.markdown("Copy these tables from the simulation (each paste contains the full history):")
    st.markdown(bullets([
        "**Required:** price history, unit sales, market demand, capacity utilization, "
        "net income *total* and *per rented vehicle* (Orlando and Miami each).",
        "**Optional:** fleet size, net income *per vehicle per month* (used for the unit-economics "
        "chart) and *% of revenue*.",
    ]))
    st.markdown(bullets([
        "Paste one table at a time, **or** drop the saved .txt files, **or** import a folder.",
        "Re-importing the same months is safe: values merge by month.",
        "Any change to an earlier month is flagged.",
    ]))

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
latest, prev = data.months[-1], data.months[-2]    # always: this round vs the previous round

st.caption(f"Analysing **{latest}** against **{prev}** · months in the data: "
           f"{', '.join(data.months)}")
incomplete = [m for m in store.months() if m not in months_ok]
if incomplete:
    st.warning(f"Skipped (missing required tables): {', '.join(incomplete)}. "
               "See the Import & data tab.")
for note in insights.caveats(data):
    st.caption(f"ℹ️ {note}")

with st.sidebar:
    st.header("View")
    city_sel = st.radio("City", CITY_OPTIONS, key="city_sel", help="Florida = Orlando + Miami.")
    daypart_sel = st.radio("Day period", DAYPART_OPTIONS, key="daypart_sel")
sel_cities, sel_dayparts, sel_segs = scope(city_sel, daypart_sel)
multi_city = len(sel_cities) > 1
whole_city = len(sel_dayparts) == len(DAYPARTS)
CITY_LEVEL_NOTE = ("City-level view: it covers both day periods, because the simulation reports "
                   "these numbers for the whole city.")
st.caption(f"Showing: **{' + '.join(sel_cities)}** · **{' + '.join(sel_dayparts)}**")

pvu = model.price_vs_util(data)
dvu = model.demand_vs_util(data)
segs_by_case = {c: model.whatif_segments(data, latest, c, pvu, dvu) for c in model.CASES}
guides = {c: model.price_guide(data, c, latest, segs_by_case) for c in CITIES}
bridges = {c: model.profit_bridge(data, c, prev, latest) for c in CITIES}
bes = {c: model.break_even(data, c, latest, prev) for c in CITIES}
ue = model.unit_economics(data)
contrib = model.weekday_weekend_contribution(data)
dem_readouts = insights.demand_readouts(data, dvu)

tabs = st.tabs(["Overview", "Price planner", "Price vs Utilization", "Demand vs Utilization",
                "Profit bridge", "Break-even & economics", "Import & data"])

# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #
with tabs[0]:
    perf, perf_label = model.scope_performance(data, sel_cities, sel_dayparts)
    total_col = "Florida" if multi_city else sel_cities[0]
    tot = perf[total_col]
    st.metric(f"{total_col} {perf_label.lower()}, {latest}", charts.money(tot[latest]),
              charts.money(tot[latest] - tot[prev], True) + f" vs {prev}")
    if not whole_city:
        st.caption("Pre-tax profit is only reported for a whole city, so with one day period "
                   f"selected the profit figures are that period's contribution ({perf_label.lower()}).")
    st.plotly_chart(charts.scope_profit_chart(perf, perf_label), width="stretch", key="ov_scope")
    cols = st.columns(len(sel_cities))
    for col, city in zip(cols, sel_cities):
        with col:
            st.subheader(city)
            m1, m2, m3 = st.columns(3)
            m1.metric(f"{latest} {perf_label.lower()}", charts.money(perf[city][latest]),
                      charts.money(perf[city][latest] - perf[city][prev], True) + f" vs {prev}")
            for mcol, dp in zip((m2, m3), sel_dayparts):
                mcol.metric(f"{dp} util", f"{data.utilization(city, dp)[latest]:.0%}")
            pp = model.price_vs_profit(data, city)
            pp["Pre-tax profit"] = perf[city]
            st.plotly_chart(charts.price_and_profit(pp, sel_dayparts, perf_label),
                            width="stretch", key=f"ov_{city}")
    st.subheader("Key readouts")
    st.markdown("\n".join(nested(insights.pick_readout(guides[c], data, latest)) for c in sel_cities))
    lines = [insights.bridge_readout(bridges[c]) for c in sel_cities]
    if multi_city:
        lines.insert(0, insights.bridge_readout(model.combine_bridges([bridges[c] for c in sel_cities])))
    lines += [insights.break_even_readout(bes[c]) for c in sel_cities]
    if "Weekend" in sel_dayparts:
        lines += [x for c in sel_cities if (x := insights.weekend_readout(data, c, latest))]
    st.markdown(bullets(lines))
    if not whole_city:
        st.caption(CITY_LEVEL_NOTE + " (Bridge, break-even and the price suggestion above.)")

# --------------------------------------------------------------------------- #
# Price planner
# --------------------------------------------------------------------------- #
with tabs[1]:
    cautious_segs = segs_by_case[model.CASE_GAP_ONLY]
    optimistic_segs = segs_by_case[model.CASE_DEMAND_ADJ]
    st.subheader("Suggested prices")
    st.markdown(bullets([
        "Every projection is shown under **two assumptions** about how much utilization drops "
        "when price rises. The truth is probably between them.",
        "**Cautious:** all of the utilization change is credited to price (price matters most).",
        "**Optimistic:** only what is left after removing demand is credited to price "
        "(price matters least).",
        "**Suggested price** = the weekday/weekend pair with the best profit in the *worse* of "
        "the two cases, so it holds up whichever assumption is right.",
    ]))
    st.markdown("\n".join(nested(insights.pick_readout(guides[c], data, latest)) for c in sel_cities))

    def fill_suggested() -> None:
        for city in CITIES:
            st.session_state[f"plan_{latest}_{(city, 'Weekday')}"] = float(guides[city].pick_weekday)
            st.session_state[f"plan_{latest}_{(city, 'Weekend')}"] = float(guides[city].pick_weekend)

    st.divider()
    st.subheader(f"Price planner (starting from {latest} actuals)")
    st.button("Fill with suggested prices", on_click=fill_suggested)
    # Segments outside the current view keep their actual price, so every projection stays whole.
    prices: dict[tuple[str, str], float] = {seg: float(cautious_segs[seg].price0) for seg in SEGMENTS}
    cols = st.columns(len(sel_segs))
    for col, seg in zip(cols, sel_segs):
        s = cautious_segs[seg]
        comp = data.price(seg[0], seg[1], "Comp")[latest]
        prices[seg] = col.number_input(
            f"{s.name} ($)", value=float(s.price0), step=1.0, min_value=1.0,
            key=f"plan_{latest}_{seg}")
        col.caption(f"actual ${s.price0:.0f} · Comp ${comp:.0f} · util {s.util0:.0%}")
    scen = {c: model.scenario_profit(data, latest, segs_by_case[c], prices) for c in model.CASES}

    def profit_metrics(container, title: str, cities: list[str]) -> None:
        container.markdown(f"**{title}**")
        m1, m2 = container.columns(2)
        for mcol, case in zip((m1, m2), model.CASES):
            profit = sum(scen[case][c]["profit"] for c in cities)
            diff = profit - sum(scen[case][c]["actual"] for c in cities)
            mcol.metric(f"Profit, {model.CASE_LABELS[case].lower()}", charts.money(profit),
                        charts.money(diff, True) + f" vs {latest}",
                        delta_color="off" if abs(diff) < 1 else "normal")

    if multi_city:
        profit_metrics(st, "Florida (Orlando + Miami)", sel_cities)
    cols = st.columns(len(sel_cities))
    for col, city in zip(cols, sel_cities):
        with col:
            profit_metrics(st, city, [city])
            rows = []
            for dp in sel_dayparts:
                row = {"Segment": dp}
                for case in model.CASES:
                    d = scen[case][city]["detail"][dp]
                    lab = model.CASE_LABELS[case]
                    row[f"Utilization ({lab.lower()})"] = f"{d['utilization']:.0%}"
                    row[f"Δ profit ({lab.lower()})"] = charts.money(d["delta"], True)
                rows.append(row)
            col.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if not whole_city:
        st.caption("Profit totals are for the whole city; the day period not shown stays at its "
                   f"{latest} price.")
    for seg in sel_segs:
        if (not guides[seg[0]].measurable[seg[1]]
                and abs(prices[seg] - cautious_segs[seg].price0) >= 0.5):
            st.warning(f"{cautious_segs[seg].name}: price sensitivity can't be measured, so this "
                       "projection assumes **no volume is lost**. Treat it as a ceiling, not a "
                       "forecast.")
    st.caption("Rentals scale with utilization; variable cost per rental is held constant; "
               "raising price never increases utilization.")

    st.divider()
    st.subheader("Profit you can count on: weekday × weekend price")
    st.markdown(bullets([
        "Each cell is the **worse** of the two cases' profit for that price pair.",
        "Centre cell = current prices (orange outline). Best cell (black outline) = the "
        "suggested prices.",
    ]))
    if not whole_city:
        st.caption(CITY_LEVEL_NOTE)
    cols = st.columns(len(sel_cities))
    for col, city in zip(cols, sel_cities):
        with col:
            st.markdown(f"**{city}**")
            g = guides[city]
            if not any(g.measurable.values()):
                st.info("No grid: price sensitivity can't be measured in either day period.")
                continue
            st.plotly_chart(charts.whatif_heatmap(g.worst), width="stretch", key=f"wi_h_{city}")
            for dp in g.held:
                st.caption(f"Blank cells: {dp.lower()} price held (sensitivity unmeasurable).")

    st.subheader("Profit by price: one segment at a time")
    st.markdown(bullets([
        "Each line changes only that segment's price; the orange dot is the current price.",
        "Where the two lines are far apart, the data can't yet tell price from demand.",
    ]))
    st.plotly_chart(charts.whatif_lines(segs_by_case, sel_segs), width="stretch", key="wi_lines")
    st.markdown("**Slopes used** (util pts per +$1 of price, capped at 0):\n" + bullets(
        f"{cautious_segs[seg].name}: not measurable yet, price held"
        if cautious_segs[seg].slope_used >= 0 else
        f"{cautious_segs[seg].name}: cautious {cautious_segs[seg].slope_used:+.1f}, "
        f"optimistic {optimistic_segs[seg].slope_used:+.1f}" for seg in sel_segs))

# --------------------------------------------------------------------------- #
# Price vs Utilization
# --------------------------------------------------------------------------- #
with tabs[2]:
    st.markdown(bullets([
        "**Slope** = utilization points per +$1 of Univ–Comp price gap (negative: being "
        "pricier costs utilization). This is the *cautious* assumption.",
        "**R²** = share of utilization swings the gap alone explains.",
        "Demand moves at the same time, so check the next tab before concluding.",
    ]))
    ro = insights.price_readouts(pvu)
    for seg in sel_segs:
        p = pvu[seg]
        st.markdown(f"#### {p.name}")
        a, b = st.columns(2)
        a.plotly_chart(charts.price_and_util_by_month(p), width="stretch", key=f"pu1_{seg}")
        b.plotly_chart(charts.util_vs_gap(p), width="stretch", key=f"pu2_{seg}")
        sl = "n/a" if p.slope_pts is None else f"{p.slope_pts:+.1f} util pts per +$1 gap"
        r = "n/a" if p.r2 is None else f"{p.r2:.2f}"
        st.markdown(bullets([f"**Gap slope:** {sl}", f"**R²:** {r}", *ro[seg]]))

# --------------------------------------------------------------------------- #
# Demand vs Utilization
# --------------------------------------------------------------------------- #
with tabs[3]:
    st.markdown(bullets([
        "Utilization is regressed on demand; what is left over is what price (the Univ–Comp "
        "gap) might explain.",
        "**Price slope** = the effect of price after demand is removed. This is the "
        "*optimistic* assumption.",
        "**Demand** per day period = units sold + unfilled orders (assigned to the busier "
        "day period). Unit sales are rounded to thousands, so expect about ±0.5%.",
    ]))
    for seg in sel_segs:
        d = dvu[seg]
        st.markdown(f"#### {d.name}")
        a, b, c = st.columns(3)
        a.plotly_chart(charts.util_vs_demand(d), width="stretch", key=f"dv1_{seg}")
        b.plotly_chart(charts.price_effect_after_demand(d), width="stretch", key=f"dv2_{seg}")
        c.plotly_chart(charts.indexed_trends(d), width="stretch", key=f"dv3_{seg}")
        r2 = "n/a" if d.r2_demand is None else f"{d.r2_demand:.2f}"
        ds = "n/a" if d.demand_slope_pts_per_10k is None else f"{d.demand_slope_pts_per_10k:+.1f}"
        ps = "n/a" if d.price_slope_pts is None else f"{d.price_slope_pts:+.1f}"
        st.markdown(bullets([
            f"**R² vs demand:** {r2}",
            f"**Demand slope:** {ds} util pts per 10K orders",
            f"**Price slope (after demand):** {ps} util pts per +$1 gap",
            *dem_readouts[seg]]))
    if "Miami" in sel_cities:
        st.markdown("#### Miami: sales vs unfilled orders")
        st.plotly_chart(charts.sales_vs_unfilled(
            data.months, data.market("Miami", "sales"), data.market("Miami", "unfilled"),
            data.utilization("Miami", "Weekday")), width="stretch", key="miami_unfilled")

# --------------------------------------------------------------------------- #
# Profit bridge
# --------------------------------------------------------------------------- #
with tabs[4]:
    st.markdown(f"What moved profit from **{prev}** to **{latest}**:")
    st.markdown(bullets([
        "**Price effect** = price change × new volume.",
        "**Volume effect** = volume change × old contribution per rental.",
        "**Variable cost / rental** and **fixed costs** are straight differences.",
        "**Rounding** = any remainder from rounding in the simulation's reported numbers.",
    ]))
    if not whole_city:
        st.caption(CITY_LEVEL_NOTE)
    shown = {c: bridges[c] for c in sel_cities}
    if multi_city:
        shown = {"Florida": model.combine_bridges(list(shown.values())), **shown}
    cols = st.columns(len(shown))
    for col, (name, br) in zip(cols, shown.items()):
        with col:
            st.subheader(name)
            st.plotly_chart(charts.bridge_chart(br), width="stretch", key=f"br_{name}")
            st.caption(insights.bridge_readout(br))

# --------------------------------------------------------------------------- #
# Break-even & economics
# --------------------------------------------------------------------------- #
with tabs[5]:
    st.subheader(f"Break-even utilization ({latest} volumes & costs)")
    st.markdown(bullets([
        f"**@ {latest} prices:** profit at each utilization level with the current prices.",
        f"**@ {prev} prices:** the same, using last round's contribution per rental.",
    ]))
    if not whole_city:
        st.caption(CITY_LEVEL_NOTE)
    cols = st.columns(len(sel_cities))
    for col, city in zip(cols, sel_cities):
        with col:
            st.markdown(f"**{city}**")
            st.plotly_chart(charts.break_even_chart(bes[city]), width="stretch", key=f"be_{city}")
            st.caption(insights.break_even_readout(bes[city]))
    st.subheader("Revenue per vehicle per month: where it goes")
    cols = st.columns(len(sel_cities))
    for col, city in zip(cols, sel_cities):
        col.markdown(f"**{city}**")
        col.plotly_chart(charts.unit_economics_chart(ue, city), width="stretch", key=f"ue_{city}")
    st.subheader("Weekday vs weekend profit contribution")
    cols = st.columns(len(sel_cities))
    for col, city in zip(cols, sel_cities):
        col.markdown(f"**{city}**")
        col.plotly_chart(charts.contribution_chart(contrib, city), width="stretch", key=f"ct_{city}")
    with st.expander("Tables"):
        st.dataframe(ue, hide_index=True, width="stretch")
        st.dataframe(contrib, hide_index=True, width="stretch")

with tabs[6]:
    data_tab()
