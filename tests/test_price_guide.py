"""The price guide: suggestions must hold up under both sensitivity assumptions."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pricing import insights, model
from pricing.data import SimData
from pricing.model import CASE_DEMAND_ADJ, CASE_GAP_ONLY
from pricing.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ctx():
    store = Store(ROOT / "data" / "_test_facts.csv")
    store.clear()
    store.add_folder(ROOT / "sample_data")
    data = SimData(store.facts)
    pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
    segs = {c: model.whatif_segments(data, "Oct", c, pvu, dvu) for c in model.CASES}
    return data, segs


def test_worst_case_is_never_better_than_either_case(ctx):
    data, segs = ctx
    g = model.price_guide(data, "Orlando", "Oct", segs)
    worst = g.worst.profit.values
    assert np.all(worst <= g.cautious.profit.values + 1e-6)
    assert np.all(worst <= g.optimistic.profit.values + 1e-6)


def test_orlando_cases_disagree_on_direction_so_hold(ctx):
    data, segs = ctx
    g = model.price_guide(data, "Orlando", "Oct", segs)
    # Cautious says cut prices, optimistic says raise them: only holding is safe in both.
    assert g.cautious.best_vs_actual > 0 and g.optimistic.best_vs_actual > g.cautious.best_vs_actual
    assert g.is_hold and g.held == []
    assert (g.pick_weekday, g.pick_weekend) == (41, 34)


def test_miami_is_held_because_sensitivity_is_unmeasurable(ctx):
    data, segs = ctx
    g = model.price_guide(data, "Miami", "Oct", segs)
    assert g.measurable == {"Weekday": False, "Weekend": False}
    assert (g.pick_weekday, g.pick_weekend) == (46, 36)           # current prices, not +$6
    assert int(np.isfinite(g.worst.profit.values).sum()) == 1     # only the current-price cell
    lines = insights.pick_readout(g, data, "Oct")
    assert "no price recommendation" in lines[0]
    assert any("64,000 unfilled orders" in l for l in lines)


def test_when_both_cases_agree_the_pick_is_that_cases_best(ctx):
    data, segs = ctx
    same = {CASE_GAP_ONLY: segs[CASE_GAP_ONLY], CASE_DEMAND_ADJ: segs[CASE_GAP_ONLY]}
    g = model.price_guide(data, "Orlando", "Oct", same)
    best = model.whatif_grid(data, "Orlando", "Oct", segs[CASE_GAP_ONLY])
    assert (g.pick_weekday, g.pick_weekend) == (best.best_weekday, best.best_weekend)
    assert g.cautious_delta == pytest.approx(g.optimistic_delta)
    assert g.cautious_delta == pytest.approx(best.best_vs_actual)
    assert not g.is_hold
