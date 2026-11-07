"""Readouts: headline first, supporting numbers after."""
from __future__ import annotations

from pathlib import Path

import pytest

from pricing import insights, model
from pricing.config import CITIES
from pricing.data import SimData
from pricing.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ctx():
    store = Store(ROOT / "data" / "_test_facts.csv")
    store.clear()
    store.add_folder(ROOT / "sample_data")
    data = SimData(store.facts, store.complete_months())
    latest, prev = data.months[-1], data.months[-2]
    pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
    segs = {c: model.whatif_segments(data, latest, c, pvu, dvu) for c in model.CASES}
    return dict(data=data, latest=latest, prev=prev, pvu=pvu, dvu=dvu, segs=segs,
                guides={c: model.price_guide(data, c, latest, segs) for c in CITIES},
                bridges={c: model.profit_bridge(data, c, prev, latest) for c in CITIES},
                bes={c: model.break_even(data, c, latest, prev) for c in CITIES})


def test_profit_insight_direction_and_driver(ctx):
    for city in CITIES:
        b = ctx["bridges"][city]
        head, support = insights.profit_insight(b)
        assert ("rose" if b.end > b.start else "fell") in head
        assert "mainly from" in head
        assert all(w in support for w in ("Price", "volume", "fixed costs"))


def test_break_even_insight_wording(ctx):
    for city in CITIES:
        be = ctx["bes"][city]
        head, support = insights.break_even_insight(be)
        cushion = be.actual_util - be.break_even[f"@ {be.month} prices"]
        assert ("above" if cushion >= 0 else "below") in head
        assert "actual utilization" in support


def test_price_insight_miami_and_orlando(ctx):
    d, m = ctx["data"], ctx["latest"]
    assert "no price recommendation" in insights.price_insight(ctx["guides"]["Miami"], d, m)[0].lower()
    assert "hold" in insights.price_insight(ctx["guides"]["Orlando"], d, m)[0].lower()


def test_idle_weekend_insight_empty_when_busy(ctx):
    d, m = ctx["data"], ctx["latest"]
    for city in CITIES:
        got = insights.idle_weekend_insight(d, city, m)
        assert (got == []) == (d.utilization(city, "Weekend")[m] >= 0.5)


def test_city_readouts_weekend_only_when_selected(ctx):
    kw = dict(data=ctx["data"], month=ctx["latest"])
    args = ("Orlando", ctx["guides"]["Orlando"], ctx["bridges"]["Orlando"], ctx["bes"]["Orlando"])
    wd = insights.city_readouts(*args, dayparts=["Weekday"], **kw)
    both = insights.city_readouts(*args, dayparts=["Weekday", "Weekend"], **kw)
    assert len(wd) == 3 and len(both) >= 3
    assert not any("idle" in i[0] for i in wd)


def test_slope_insight_unmeasurable_segment(ctx):
    c, o = ctx["segs"][model.CASE_GAP_ONLY], ctx["segs"][model.CASE_DEMAND_ADJ]
    out = insights.slope_insight(c, o, [("Miami", "Weekend")])
    assert "not measurable" in out[0][0]


def test_segment_insights_carry_numbers(ctx):
    ro = insights.price_readouts(ctx["pvu"])
    for seg, p in ctx["pvu"].items():
        out = insights.price_segment_insight(p, ro[seg])
        assert out[0] and any("R²" in line for line in out)
    dro = insights.demand_readouts(ctx["data"], ctx["dvu"])
    for seg, d in ctx["dvu"].items():
        out = insights.demand_segment_insight(d, dro[seg])
        assert out[0] and any("R² vs demand" in line for line in out)
    miami_we = insights.price_segment_insight(ctx["pvu"][("Miami", "Weekend")],
                                              ro[("Miami", "Weekend")])
    assert "can't be measured" in miami_we[0]


def test_price_insight_drops_city_prefix(ctx):
    d, m = ctx["data"], ctx["latest"]
    for city in CITIES:
        lines = insights.price_insight(ctx["guides"][city], d, m)
        assert all(not line.startswith(f"{city}") and not line.startswith(f"**{city}") for line in lines)
    assert insights.price_insight(ctx["guides"]["Miami"], d, m)[1].startswith("Weekday price held")


def test_slope_insight_support_explains_each_case(ctx):
    c, o = ctx["segs"][model.CASE_GAP_ONLY], ctx["segs"][model.CASE_DEMAND_ADJ]
    head, support = insights.slope_insight(c, o, [("Orlando", "Weekday")])[0]
    assert "to" in head and "per +$1 of price" in head
    assert "cautious" in support.lower() and "optimistic" in support.lower()


def test_tones_green_red_yellow(ctx):
    d, m = ctx["data"], ctx["latest"]
    for city in CITIES:
        b = ctx["bridges"][city]
        assert insights.profit_insight(b).tone == (insights.GOOD if b.end > b.start else insights.BAD)
        be = ctx["bes"][city]
        cushion = be.actual_util - be.break_even[f"@ {be.month} prices"]
        assert insights.break_even_insight(be).tone == (insights.GOOD if cushion >= 0 else insights.BAD)
    # hold / no recommendation / explanatory readouts are neutral (yellow)
    assert insights.price_insight(ctx["guides"]["Orlando"], d, m).tone == insights.INFO
    assert insights.price_insight(ctx["guides"]["Miami"], d, m).tone == insights.INFO
    c, o = ctx["segs"][model.CASE_GAP_ONLY], ctx["segs"][model.CASE_DEMAND_ADJ]
    assert all(i.tone == insights.INFO for i in insights.slope_insight(c, o, [("Orlando", "Weekday")]))
    ro = insights.price_readouts(ctx["pvu"])
    assert insights.price_segment_insight(ctx["pvu"][("Orlando", "Weekday")],
                                          ro[("Orlando", "Weekday")]).tone == insights.INFO
    # a plain list of strings to code that ignores the tone
    assert isinstance(insights.profit_insight(ctx["bridges"]["Orlando"]), list)


def test_price_headline_is_capitalised(ctx):
    d, m = ctx["data"], ctx["latest"]
    assert insights.price_insight(ctx["guides"]["Orlando"], d, m)[0].startswith("**Hold current prices.")
    assert insights.price_insight(ctx["guides"]["Miami"], d, m)[0].startswith("**No price recommendation.")


def test_profit_oneliner_is_a_single_line_with_the_four_effects(ctx):
    line = insights.profit_oneliner("Orlando", ctx["bridges"]["Orlando"])
    assert chr(10) not in line and line.startswith("**Orlando:**")
    assert all(w in line for w in ("price", "volume", "variable cost", "fixed costs"))


def test_whatif_lines_one_figure_per_segment_with_a_line_per_case(ctx):
    from pricing import charts
    from pricing.config import SEGMENTS
    figs = charts.whatif_lines(ctx["segs"], SEGMENTS)
    assert list(figs) == list(SEGMENTS)
    cases = lambda k: [t.name for t in figs[k].data if t.name != "Actual price"]
    assert len(cases(("Orlando", "Weekday"))) == 2
    assert cases(("Miami", "Weekend")) == []               # unmeasurable: no curve


def test_overview_unfilled_orders_axis_starts_at_zero_and_grows_down():
    import pandas as pd
    from pricing import charts
    idx = ["Jul", "Aug"]
    df = pd.DataFrame({"Weekday price": [40.0, 41.0], "Weekday comp price": [40.0, 40.0],
                       "Weekday utilization": [.8, .9], "Weekend price": [30.0, 31.0],
                       "Weekend comp price": [30.0, 30.0], "Weekend utilization": [.7, .8],
                       "Pre-tax profit": [1e5, 2e5], "Unfilled orders": [0.0, 5e4],
                       "Unfilled share": [0.0, .1], "Fleet size": [1e3, 1e3]}, index=idx)
    fig = charts.price_and_profit(df, ("Weekday", "Weekend"))
    ax = fig.layout[f"yaxis{len(fig.data) and 5}"]
    assert ax.autorange == "reversed" and ax.rangemode == "tozero"
