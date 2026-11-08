"""Pricing Simulation Dashboard.   Run:  streamlit run app.py"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from pricing import charts, insights, model
from pricing.config import (CITIES, CITY_OPTIONS, COPY_LIST, DAYPART_OPTIONS, DAYPARTS,
                            SEGMENTS, item_name, next_month, scope)
from pricing.data import SimData
from pricing.parsers import guess_city_from_name
from pricing.store import ImportReport, Store

ROOT = Path(__file__).parent
DATA_FILE = Path(os.environ.get("PRICING_SIM_DATA") or ROOT / "data" / "facts.csv")
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


TONE_COLOR = {insights.GOOD: "green", insights.BAD: "red", insights.INFO: "yellow"}


def nested(lines: list[str]) -> str:
    """First line as a bullet, in a font color by tone (green good news, red bad news, orange other),
    with the rest as sub-bullets beneath it."""
    color = TONE_COLOR[getattr(lines, "tone", insights.INFO)]
    return "\n".join([f"- :{color}[{lines[0]}]", *(f"    - {l}" for l in lines[1:])])


def city_block(name: str, items: list[list[str]]) -> None:
    """A city heading, then each insight as a headline bullet with its support beneath."""
    st.markdown(f"**{name}**")
    st.markdown("\n".join(nested(i) for i in items if i))


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
def import_pasted() -> None:
    """text_area callback: import everything in the box, then empty it (re-importing is safe)."""
    st_store: Store = st.session_state["store"]
    text = st.session_state.get("paste_text", "")
    if not text.strip():
        return
    rep = st_store.add_pasted(text)
    if rep.imported:
        st_store.save()
        st.session_state["paste_text"] = ""          # keep the text only if nothing was usable
    st.session_state["pending_city"] = rep.unresolved
    st.session_state["last_report"] = rep


def copy_list_markdown(month: str | None) -> str:
    """The tabs to copy, with a tick for each one already held for the newest month."""
    head = f"| # | Copy this tab | Select | {month or 'Status'} |"
    rows = [head, "|:-:|---|---|:-:|"]
    for n, (table, city, tab, pick) in enumerate(COPY_LIST, 1):
        have = month is not None and item_name(table, city) not in store.missing(month)
        rows.append(f"| {n} | **{tab}** | {pick} | {':green[✓]' if have else ':red[✗]'} |")
    return "\n".join(rows)


def data_tab() -> None:
    if "last_report" in st.session_state:
        show_report(st.session_state.pop("last_report"))
    st.subheader("Import a new month")
    newest = store.newest_month()
    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown(f"**Copy these {len(COPY_LIST)} tabs from the simulation**")
        st.markdown(copy_list_markdown(newest), unsafe_allow_html=True)  # <br> in the Select column
        if newest and store.missing(newest):
            st.warning(f"{newest} is still missing: {', '.join(store.missing(newest))}.")
        elif newest:
            st.success(f"Data is complete through {newest}. After the next round, paste the new "
                       "tables.")
        st.caption("Nothing else is needed: per-vehicle and % screens and the Florida "
                   "net income view are not used.")
    with c2:
        st.markdown("**Paste them all here**")
        st.text_area("Paste copied tables (tab-separated)", height=210, key="paste_text",
                     label_visibility="collapsed", on_change=import_pasted,
                     placeholder="Copy a tab, paste it here, copy the next, paste again…\n"
                                 "Any order. Then press Ctrl+Enter (or click outside this box).")
        st.markdown(bullets([
            "After the last paste press **Ctrl+Enter** or click outside the box: it imports "
            "by itself, no button.",
            "Each net income city is detected from its numbers.",
            "Fleet size is needed every month: you can change capacity in the simulation, "
            "and the header shows it.",
            "Each paste holds the full history, so re-importing is safe; changes to earlier "
            "months are flagged.",
        ]))
    pending = st.session_state.get("pending_city") or []
    if pending:
        st.warning(f"{len(pending)} net income table(s) could not be matched to a city "
                   "(the prices and unit sales to match them with are not loaded yet, or it is "
                   "a screen that can't be matched). Choose the city:")
        picks = [st.selectbox(f"Net income table {i}", CITIES, index=None,
                              placeholder="Choose a city", key=f"pending_city_{i}")
                 for i in range(1, len(pending) + 1)]
        if st.button("Import with these cities", disabled=any(p is None for p in picks)):
            rep = ImportReport()
            for block, pick in zip(pending, picks):
                store.add_pasted(block, city=pick, report=rep)
            st.session_state["pending_city"] = []
            finish_import(rep)

    with st.expander("Other ways to import (saved .txt files, a folder)"):
        files = st.file_uploader("Upload .txt tables", type=["txt"], accept_multiple_files=True)
        if files and st.button(f"Import {len(files)} file(s)"):
            rep = ImportReport()
            for f in files:
                store.add_pasted(f.getvalue().decode("utf-8-sig"), label=f.name, report=rep)
            finish_import(rep)
        folder = st.text_input("Folder of .txt files", value=str(ROOT / "inbox"),
                               help="Net income files need 'orlando' or 'miami' in the file "
                                    "name, unless they are the total screen (detected).")
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
st.markdown("""<style>
/* One spacing rule for the whole app: blocks are separated only by the flex gap below.
   Streamlit pads paragraphs and cancels it with a negative margin on the container; we remove both,
   otherwise a text block loses part of its gap and spacing looks uneven. */
[data-testid="stMainBlockContainer"] { padding-top: 2.5rem; padding-bottom: 2rem; }
[data-testid="stVerticalBlock"] { gap: 0.4rem; }
[data-testid="stHorizontalBlock"] { gap: 0.75rem; }
[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[data-testid="stMarkdownContainer"] p { line-height: 1.4; margin: 0 0 0.4rem 0; }
[data-testid="stMarkdownContainer"] p:last-child { margin-bottom: 0; }
[data-testid="stMarkdownContainer"] ul, [data-testid="stMarkdownContainer"] ol { margin: 0; padding-bottom: 0; }
[data-testid="stMarkdownContainer"] li { line-height: 1.4; margin-bottom: 0; }
[data-testid="stCaptionContainer"] { line-height: 1.35; margin: 0; padding: 0; }
[data-testid="stCaptionContainer"] p { margin: 0; }
[data-testid="stMarkdownContainer"] table { margin: 0; }
[data-testid="stHeading"] { margin: 0; padding: 0; }
h1 { padding: 0 0 0.25rem 0; }
h2, h3 { padding: 0.6rem 0 0 0; }
hr { margin: 0.2rem 0; }
[data-testid="stMetric"] { padding: 0; gap: 0; }
[data-testid="stTabs"] [data-baseweb="tab-panel"] { padding-top: 0.6rem; }
[data-testid="stAlert"] { padding: 0.4rem 0.75rem; }
[data-testid="stExpander"] details summary { padding: 0.4rem 0.75rem; }
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] { gap: 0.3rem; }
</style>""", unsafe_allow_html=True)
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
for m in (m for m in store.months() if m not in months_ok):
    st.warning(f"Missing for {m}: {', '.join(store.missing(m))}. Showing {latest} against {prev} "
               "until they are pasted (Import & data tab).", title=f"{m} is incomplete")
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
research = model.research_sensitivity(data)


def research_lines(segments) -> list[insights.Insight]:
    """Market-research one-liners for these segments (only where the pattern shows)."""
    return [insights.Insight([line]) for seg in segments
            if (line := insights.research_oneliner(research[seg]))]

# --------------------------------------------------------------------------- #
# Always-visible header: price stance + last month's status (every tab, every view)
# --------------------------------------------------------------------------- #
cautious_segs = segs_by_case[model.CASE_GAP_ONLY]
optimistic_segs = segs_by_case[model.CASE_DEMAND_ADJ]
status = model.status_snapshot(data, latest, prev, segs_by_case)


def suggested_price(seg: tuple[str, str]) -> float:
    """The guide's pick for a segment (the current price when it recommends holding)."""
    g = guides[seg[0]]
    return float(g.pick_weekday if seg[1] == "Weekday" else g.pick_weekend)


def reset_plan() -> None:
    """Back to last month's prices and fleet sizes (callback: widget state can't be written after
    the widgets render)."""
    for seg in SEGMENTS:
        st.session_state[f"plan_{latest}_{seg}"] = float(status.segments[seg].price)
    for city in CITIES:
        cap = status.segments[(city, "Weekday")].capacity
        if cap is not None:
            st.session_state[f"plan_cap_{latest}_{city}"] = float(cap)


# The planner boxes start at the suggested prices. If the suggestion changes (data restated or
# re-imported), the boxes follow it; otherwise the team's edits stay.
_sig = tuple(suggested_price(seg) for seg in SEGMENTS)
if st.session_state.get(f"plan_sig_{latest}") != _sig:
    st.session_state[f"plan_sig_{latest}"] = _sig
    for seg, p in zip(SEGMENTS, _sig):
        st.session_state[f"plan_{latest}_{seg}"] = p


def tone(text: str, good: bool | None) -> str:
    """Green = good, red = bad, none = neutral."""
    return text if good is None else f":{'green' if good else 'red'}[{text}]"


def sign(v: float) -> bool | None:
    """Good/bad for tone(); a $0 result is neither."""
    return None if abs(v) < 0.5 else v > 0


def flag(text: str) -> str:
    return f":yellow[{text}]"                      # yellow = important, needs attention


def delta_text(v: float, fmt) -> str:
    return "(" + tone(fmt(v), None if abs(v) < 0.5 else v > 0) + ")"


next_m = next_month(latest)
head_l, head_r = st.columns([5, 1], vertical_alignment="center")
head_l.markdown(f"**Our prices and capacity for {next_m}**",
                help=f"Prices start at the suggested prices (see the Price planner tab).\n"
                     f"Reset puts back {latest}'s prices and fleet sizes.")
head_r.button(f"Reset to {latest} prices", on_click=reset_plan, key="reset_plan", width="stretch")
prices: dict[tuple[str, str], float] = {}
fleets: dict[str, float] = {}
# Row 1: the four prices. Row 2: one fleet size per city, each box as wide as that city's two prices.
price_cols = st.columns(len(SEGMENTS))
for col, seg in zip(price_cols, SEGMENTS):
    s, sg = cautious_segs[seg], status.segments[seg]
    prices[seg] = col.number_input(f"{s.name} ($)", step=1.0,       # value set above via session state
                                   min_value=1.0, key=f"plan_{latest}_{seg}")
    chg = prices[seg] - sg.price
    col.caption(f"{latest}: {charts.price(sg.price)}" + ("" if abs(chg) < 0.005 else
                " · " + flag(f"{charts.price(chg, True)}")))
for col, city in zip(st.columns(len(CITIES)), CITIES):
    cap_now = status.segments[(city, "Weekday")].capacity
    if cap_now is None:
        col.caption(f"{city}: no fleet size yet. Paste the Fleet size tab.")
        continue
    fleets[city] = col.number_input(f"{city} fleet size (vehicles)", value=float(cap_now),
                                    step=100.0, min_value=1.0, key=f"plan_cap_{latest}_{city}")
    chg = fleets[city] - cap_now
    col.caption(f"{latest}: {cap_now:,.0f}" + ("" if abs(chg) < 0.5 else
                " · " + flag(f"{chg:+,.0f}")))
scen = {c: model.scenario_profit(data, latest, segs_by_case[c], prices, fleets)
        for c in model.CASES}


def expected_range(cities: list[str]) -> str:
    """Profit range (cautious to optimistic) for these cities, with the change vs last month."""
    lo, hi = sorted(sum(scen[c][ci]["profit"] for ci in cities) for c in model.CASES)
    actual = sum(scen[model.CASES[0]][ci]["actual"] for ci in cities)
    return "  \n".join([
        f"**{charts.money(lo)} to {charts.money(hi)}**",
        ":gray[vs " + latest + " " + charts.money(actual) + "] "
        + delta_text(lo - actual, lambda v: charts.money(v, True)) + " to "
        + delta_text(hi - actual, lambda v: charts.money(v, True)),
    ])


st.markdown("Expected profit at these prices (cautious to optimistic)",
            help="Capacity is set per city.\n"
                 "Demand is capped by capacity.\n"
                 "Vehicle inventory cost is charged for each vehicle added or removed.")
for col, (name, cities) in zip(st.columns(3), [("Florida", list(CITIES))] + [(c, [c]) for c in CITIES]):
    col.markdown(f"**{name}**  \n" + expected_range(cities))

fl_cum = status.florida_cumulative
st.markdown(
    f"**Last month: {latest}** · Florida profit/loss "
    f"**{tone(charts.money(status.florida_profit), sign(status.florida_profit))}** "
    + delta_text(status.florida_delta, lambda v: charts.money(v, True))
    + " · Total since game start: "
    + ("n/a" if fl_cum is None else f"**{tone(charts.money(fl_cum), sign(fl_cum))}**")
    + " · " + " · ".join(f"{c} {charts.money(v)}" for c, v in status.city_profit.items()))
if status.since is None:
    st.caption("No game month played yet, so Florida and city profit/loss show $0 until the first month is "
               "played (read from the simulation's accumulated pre-tax profit). "
               "The cards below show each day period's contribution (before fixed costs).")
for col, seg in zip(st.columns(len(SEGMENTS)), SEGMENTS):
    sg = status.segments[seg]
    rng = sg.elasticity_range
    du = (sg.utilization - sg.utilization_prev) * 100
    dc = sg.contribution - sg.contribution_prev
    util_good = None if sg.at_capacity else sg.utilization >= 0.8
    with col.container(border=True):
        st.markdown("  \n".join([
            f"**{seg[0]} – {seg[1]}**" + ("  " + flag("⚠ at capacity") if sg.at_capacity else ""),
            f"Profit **{tone(charts.money(sg.contribution), sign(sg.contribution))}** "
            + delta_text(dc, lambda v: charts.money(v, True)),
            f"Price **{charts.price(sg.price)}** · :gray[comp {charts.price(sg.comp_price)}] "
            f"({tone(charts.price(sg.gap, True), None if abs(sg.gap) < 0.005 else sg.gap < 0)})",
            f"Utilization **{tone(f'{sg.utilization:.0%}', util_good)}** "
            + delta_text(du, lambda v: f"{v:+.0f} pts"),
            ":gray[Capacity] " + ("**n/a**" if not sg.capacity else f"**{sg.capacity:,.0f}**" + (
                "" if sg.capacity_prev is None else " " + delta_text(
                    sg.capacity - sg.capacity_prev, lambda v: f"{v:+,.0f}"))),
            ":gray[Elasticity (pts per +$1)] " + (
                flag("not measurable") if rng is None else f":gray[{rng[0]:.1f} to {rng[1]:.1f}]"),
        ]))
st.divider()

# `key` makes Streamlit remember the open tab across reruns. Without it, any change in the number of
# banners above the tabs (e.g. a "missing table" warning after a paste) resets it to Overview.
tabs = st.tabs(["Overview", "Price planner", "Price vs Utilization", "Demand vs Utilization",
                "Business vs Leisure", "Profit bridge", "Break-even & economics", "Import & data"],
               key="main_tabs")

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
    moved = ([insights.profit_oneliner("Florida", model.combine_bridges([bridges[c] for c in sel_cities]))]
             if multi_city else [])
    moved += [insights.profit_oneliner(c, bridges[c]) for c in sel_cities]
    st.markdown("  \n".join(moved),
                help=f"What moved profit from {prev} to {latest}, for the whole city (both day periods).\n"
                     "Details are in the Profit bridge tab.")
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
    if multi_city:
        city_block("Florida (Orlando + Miami)",
                   [insights.profit_insight(model.combine_bridges([bridges[c] for c in sel_cities]))])
    for city in sel_cities:
        city_block(city, insights.city_readouts(city, guides[city], bridges[city], bes[city],
                                                data, latest, sel_dayparts)
                   + research_lines([(city, dp) for dp in sel_dayparts]))
    if not whole_city:
        st.caption(CITY_LEVEL_NOTE + " (Bridge, break-even and the price suggestion above.)")

# --------------------------------------------------------------------------- #
# Price planner
# --------------------------------------------------------------------------- #
with tabs[1]:
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
    for city in sel_cities:
        city_block(city, [insights.price_insight(guides[city], data, latest)])

    st.caption("The boxes at the top of the page start at the suggested prices; the projections "
               "follow whatever is in them.")
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
        "Cities side by side, day periods stacked. Each line changes only that segment's price; "
        "the orange dot is the current price.",
        "Where the two lines are far apart, the data can't yet tell price from demand.",
    ]))
    wi_figs = charts.whatif_lines(segs_by_case, sel_segs)
    for dp in sel_dayparts:
        for col, city in zip(st.columns(len(sel_cities)), sel_cities):
            with col:
                st.markdown(f"**{city} – {dp}**")
                st.plotly_chart(wi_figs[(city, dp)], width="stretch", key=f"wi_lines_{city}_{dp}")
                st.markdown(chr(10).join(nested(i) for i in insights.slope_insight(
                    cautious_segs, optimistic_segs, [(city, dp)]) + research_lines([(city, dp)])))

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
    for city in sel_cities:
        st.markdown(f"### {city}")
        for dp in sel_dayparts:
            seg = (city, dp)
            p = pvu[seg]
            st.markdown(f"#### {p.name}")
            a, b = st.columns(2)
            a.plotly_chart(charts.price_and_util_by_month(p), width="stretch", key=f"pu1_{seg}")
            b.plotly_chart(charts.util_vs_gap(p), width="stretch", key=f"pu2_{seg}")
            st.markdown(nested(insights.price_segment_insight(p, ro[seg])))

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
    for city in sel_cities:
        st.markdown(f"### {city}")
        for dp in sel_dayparts:
            seg = (city, dp)
            d = dvu[seg]
            st.markdown(f"#### {d.name}")
            a, b, c = st.columns(3)
            a.plotly_chart(charts.util_vs_demand(d), width="stretch", key=f"dv1_{seg}")
            b.plotly_chart(charts.price_effect_after_demand(d), width="stretch", key=f"dv2_{seg}")
            c.plotly_chart(charts.indexed_trends(d), width="stretch", key=f"dv3_{seg}")
            st.markdown(nested(insights.demand_segment_insight(d, dem_readouts[seg])))
        if city == "Miami":
            st.markdown("#### Miami: sales vs unfilled orders")
            st.plotly_chart(charts.sales_vs_unfilled(
                data.months, data.market("Miami", "sales"), data.market("Miami", "unfilled"),
                data.utilization("Miami", "Weekday")), width="stretch", key="miami_unfilled")

# --------------------------------------------------------------------------- #
# Business vs Leisure (market research)
# --------------------------------------------------------------------------- #
with tabs[4]:
    st.markdown(bullets([
        "**Market research** gives Univ's share among **business** and among **leisure** customers "
        "in each day period.",
        "**Slope** = share points we gain or lose per +$1 we charge above Comp. More negative = "
        "more price sensitive.",
        "Shares are whole percentages and come from a survey (they don't match unit sales exactly), "
        "so a 1-point move is the smallest step we can see. Treat slopes as directional.",
    ]))
    for city in sel_cities:
        st.markdown(f"### {city}")
        for dp in sel_dayparts:
            f = research[(city, dp)]
            st.markdown(f"#### {f.name}")
            a, b = st.columns(2)
            a.plotly_chart(charts.research_scatter(f), width="stretch", key=f"rs1_{city}_{dp}")
            b.plotly_chart(charts.research_shares_by_month(f), width="stretch",
                           key=f"rs2_{city}_{dp}")
            st.markdown(nested(insights.research_insight(f)))
    with st.expander("Summary table"):
        rows = []
        for seg in sel_segs:
            f = research[seg]
            row = {"Segment": f.name, "Status": f.status.replace("_", " ")}
            for cust in model.CUSTOMERS:
                s, e, r2 = f.slope[cust], f.elasticity[cust], f.r2[cust]
                row[f"{cust.title()} pts per +$1"] = None if s is None else round(s, 2)
                row[f"{cust.title()} elasticity"] = None if e is None else round(e, 2)
                row[f"{cust.title()} R²"] = None if r2 is None else round(r2, 2)
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# --------------------------------------------------------------------------- #
# Profit bridge
# --------------------------------------------------------------------------- #
with tabs[5]:
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
            st.markdown(nested(insights.profit_insight(br)))

# --------------------------------------------------------------------------- #
# Break-even & economics
# --------------------------------------------------------------------------- #
with tabs[6]:
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
            st.markdown(nested(insights.break_even_insight(bes[city])))
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

with tabs[7]:
    data_tab()
