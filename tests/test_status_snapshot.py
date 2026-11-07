"""The always-visible status strip: last month's numbers per segment and Florida totals."""
from __future__ import annotations

from pathlib import Path

import pytest

from pricing import model
from pricing.config import CITIES, SEGMENTS
from pricing.data import SimData
from pricing.store import Store

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture(scope="module")
def status():
    store = Store(SAMPLE.parent / "data" / "_test_facts.csv")
    store.clear()
    store.add_folder(SAMPLE)
    data = SimData(store.facts)
    latest, prev = data.months[-1], data.months[-2]
    pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
    segs = {c: model.whatif_segments(data, latest, c, pvu, dvu) for c in model.CASES}
    return data, model.status_snapshot(data, latest, prev, segs)


def test_segments_and_prices(status):
    data, st = status
    assert st.month == data.months[-1]
    assert set(st.segments) == set(SEGMENTS)
    for (city, dp), sg in st.segments.items():
        assert sg.price == data.price(city, dp, "Univ")[st.month]
        assert sg.gap == pytest.approx(sg.price - sg.comp_price)
        assert 0 <= sg.utilization <= 1.0001


def test_florida_profit_is_sum_of_cities(status):
    _, st = status
    assert st.florida_profit == pytest.approx(sum(st.city_profit[c] for c in CITIES))


def test_cumulative_is_the_simulations_accumulated_profit(status):
    data, st = status
    expected = sum(data.net("total", c, "Accumulated Pre-Tax Profit")[st.month] for c in CITIES)
    assert st.florida_cumulative == pytest.approx(expected)


def test_miami_weekday_capacity_flag(status):
    _, st = status
    assert st.segments[("Miami", "Weekday")].at_capacity


def test_next_month_wraps_in_simulation_order():
    from pricing.config import next_month
    assert next_month("Oct") == "Nov"
    assert next_month("Jun") == "Jul"


def test_elasticity_range_is_ordered_and_capped(status):
    _, st = status
    for sg in st.segments.values():
        rng = sg.elasticity_range
        if rng is not None:
            assert rng[0] <= rng[1] <= 0
    assert st.segments[("Miami", "Weekday")].elasticity_range is None   # unmeasurable


def test_contribution_has_previous_month(status):
    data, st = status
    sg = st.segments[("Orlando", "Weekday")]
    prev = data.months[-2]
    assert sg.contribution_prev == 0          # sample months were not played: shown as $0


def test_price_format_keeps_cents_and_gap_sign():
    from pricing.charts import price
    assert price(41.0) == "$41"
    assert price(35.5) == "$35.50"
    assert price(-1.0, True) == "-$1"
    assert price(1.5, True) == "+$1.50"
    assert price(0.0, True) == "$0"


def _with_accumulated(data, values):
    """Copy of the data where Orlando's accumulated profit is `values` ({month: $}); Miami 0."""
    f = data.facts.copy()
    mask = (f["table"] == "net_income_total") & (f["field"] == "Accumulated Pre-Tax Profit")
    f.loc[mask, "value"] = 0.0
    f.loc[mask & (f["city"] == "Orlando"), "value"] = f.loc[mask & (f["city"] == "Orlando"),
                                                           "month"].map(values).fillna(0.0)
    return SimData(f, data.months)


def _status(data, **kw):
    latest, prev = data.months[-1], data.months[-2]
    pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
    segs = {c: model.whatif_segments(data, latest, c, pvu, dvu) for c in model.CASES}
    return model.status_snapshot(data, latest, prev, segs, **kw)


def test_everything_reads_zero_before_the_game_is_played(status):
    data, st = status                              # bundled sample: accumulated profit is $0
    assert model.played_months(data) == []
    assert st.florida_profit == 0 and st.florida_delta == 0 and st.florida_cumulative == 0
    assert all(v == 0 for v in st.city_profit.values())
    assert st.since is None
    assert all(s.contribution == 0 and s.contribution_prev == 0 for s in st.segments.values())
    assert st.segments[("Orlando", "Weekday")].price > 0     # prices still come from the data


def test_profit_and_loss_follow_the_accumulated_profit(status):
    data, _ = status
    d = _with_accumulated(data, {"Oct": 2_500_000.0})
    assert model.played_months(d) == ["Oct"]
    st = _status(d)
    assert st.florida_profit == pytest.approx(2_500_000) and st.florida_cumulative == pytest.approx(2_500_000)
    assert st.florida_delta == 0 + 2_500_000             # previous month's profit/loss was $0
    assert st.since == "Oct"
    assert st.segments[("Orlando", "Weekday")].contribution > 0
    d2 = _with_accumulated(data, {"Sep": 1_000_000.0, "Oct": 2_500_000.0})
    st2 = _status(d2)
    assert st2.florida_profit == pytest.approx(1_500_000)
    assert st2.florida_cumulative == pytest.approx(2_500_000)
    assert st2.florida_delta == pytest.approx(500_000)   # 1.5M this month vs 1.0M last month
    assert st2.city_profit["Orlando"] == pytest.approx(1_500_000)


def test_capacity_and_its_previous_value_come_from_fleet_size(status):
    data, st = status
    sg = st.segments[("Orlando", "Weekday")]
    assert sg.capacity == data.fleet("Orlando")[st.month] == 22400
    assert sg.capacity_prev == 22400


def _segs(data):
    latest = data.months[-1]
    pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
    return latest, model.whatif_segments(data, latest, model.CASE_GAP_ONLY, pvu, dvu)


def test_same_fleet_leaves_the_projection_unchanged(status):
    data, _ = status
    latest, segs = _segs(data)
    prices = {k: s.price0 for k, s in segs.items()}
    base = model.scenario_profit(data, latest, segs, prices)
    same = model.scenario_profit(data, latest, segs, prices,
                                 {c: segs[(c, "Weekday")].fleet0 for c in CITIES})
    for c in CITIES:
        assert same[c]["profit"] == pytest.approx(base[c]["profit"])
        assert base[c]["profit"] == pytest.approx(base[c]["actual"])


def test_a_bigger_fleet_helps_only_where_demand_is_unserved(status):
    data, _ = status
    latest, segs = _segs(data)
    prices = {k: s.price0 for k, s in segs.items()}
    base = model.scenario_profit(data, latest, segs, prices)
    big = model.scenario_profit(data, latest, segs, prices,
                                {c: segs[(c, "Weekday")].fleet0 * 1.1 for c in CITIES})
    # Miami weekday ran at 100% with unfilled orders: more cars means more rentals.
    assert big["Miami"]["detail"]["Weekday"]["rentals"] > base["Miami"]["detail"]["Weekday"]["rentals"]
    # Orlando had spare cars: rentals do not change, utilization falls.
    assert big["Orlando"]["detail"]["Weekday"]["rentals"] == pytest.approx(
        base["Orlando"]["detail"]["Weekday"]["rentals"])
    assert big["Orlando"]["detail"]["Weekday"]["utilization"] < base["Orlando"]["detail"]["Weekday"]["utilization"]
    assert big["Orlando"]["profit"] < base["Orlando"]["profit"]       # inventory cost for idle cars


def test_a_smaller_fleet_caps_rentals_and_saves_inventory_cost(status):
    data, _ = status
    latest, segs = _segs(data)
    prices = {k: s.price0 for k, s in segs.items()}
    base = model.scenario_profit(data, latest, segs, prices)
    small = model.scenario_profit(data, latest, segs, prices,
                                  {c: segs[(c, "Weekday")].fleet0 * 0.5 for c in CITIES})
    d = small["Orlando"]["detail"]["Weekday"]
    assert d["utilization"] == pytest.approx(1.0)                      # demand now exceeds capacity
    assert d["rentals"] < base["Orlando"]["detail"]["Weekday"]["rentals"]
