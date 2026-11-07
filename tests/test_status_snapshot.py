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


def test_cumulative_counts_from_october(status):
    data, st = status
    expected = sum(sum(data.net("total", c, "Pre-Tax Profit")[m] for c in CITIES)
                   for m in data.months if m in ("Oct", "Nov", "Dec"))
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
    assert sg.contribution_prev == data.net("total", "Orlando", "Weekday Contribution")[prev]


def test_price_format_keeps_cents_and_gap_sign():
    from pricing.charts import price
    assert price(41.0) == "$41"
    assert price(35.5) == "$35.50"
    assert price(-1.0, True) == "-$1"
    assert price(1.5, True) == "+$1.50"
    assert price(0.0, True) == "$0"


def test_sample_months_are_detected_and_profit_counts_only_played_months(status):
    from pricing.store import sample_months
    data, st0 = status
    store_facts = data.facts if hasattr(data, "facts") else None
    assert store_facts is not None
    sm = sample_months(store_facts, SAMPLE)
    assert set(sm) == set(data.months)             # everything here is the bundled sample
    latest, prev = data.months[-1], data.months[-2]
    pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
    segs = {c: model.whatif_segments(data, latest, c, pvu, dvu) for c in model.CASES}
    none_played = model.status_snapshot(data, latest, prev, segs, played=[])
    assert none_played.florida_profit == 0 and none_played.florida_delta == 0
    assert none_played.florida_cumulative == 0
    assert all(s.contribution == 0 and s.contribution_prev == 0
               for s in none_played.segments.values())
    # prices and utilization still come from the data
    assert none_played.segments[("Orlando", "Weekday")].price > 0
    last_only = model.status_snapshot(data, latest, prev, segs, played=[latest])
    assert last_only.florida_delta == 0                         # previous month not played
    assert last_only.florida_cumulative == pytest.approx(st0.florida_profit)
