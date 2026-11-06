"""Parity: the Python model must reproduce the Excel workbook's calculated values."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pricing import model
from pricing.config import CITIES, SEGMENTS
from pricing.data import SimData
from pricing.store import Store

ROOT = Path(__file__).resolve().parents[1]
GOLD = json.loads((ROOT / "tests" / "golden.json").read_text())


@pytest.fixture(scope="module")
def data() -> SimData:
    store = Store(ROOT / "data" / "_test_facts.csv")
    store.clear()
    report = store.add_folder(ROOT / "sample_data")
    assert not report.errors, report.errors
    return SimData(store.facts)


def approx(a, b, tol=1e-6):
    if b is None:
        assert a is None, f"expected n/a, got {a}"
    else:
        assert a == pytest.approx(b, rel=tol, abs=tol)


def test_months(data):
    assert data.months == ["Jul", "Aug", "Sep", "Oct"]
    assert not data.demand_estimated


@pytest.mark.parametrize("seg", SEGMENTS)
def test_price_vs_util(data, seg):
    res = model.price_vs_util(data)[seg]
    slope, r2 = GOLD["price_vs_util"]["|".join(seg)]
    approx(res.slope_pts, slope)
    approx(res.r2, r2)


@pytest.mark.parametrize("seg", SEGMENTS)
def test_demand_vs_util(data, seg):
    res = model.demand_vs_util(data)[seg]
    r2, dslope, pslope = GOLD["demand_vs_util"]["|".join(seg)]
    approx(res.r2_demand, r2)
    approx(res.demand_slope_pts_per_10k, dslope)
    approx(res.price_slope_pts, pslope)


@pytest.mark.parametrize("city", CITIES)
def test_bridge(data, city):
    b = model.profit_bridge(data, city, "Jul", "Oct")
    for (label, value), expected in zip(b.steps, GOLD["bridge"][city]):
        approx(value, expected, 1e-6)


def _segs(data, case):
    pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
    return model.whatif_segments(data, "Oct", case, pvu, dvu)


def test_whatif_slopes_and_deltas(data):
    assert GOLD["whatif_case_in_workbook"] == model.CASE_GAP_ONLY
    segs = _segs(data, model.CASE_GAP_ONLY)
    for seg, expected in zip(SEGMENTS, GOLD["whatif_slopes_used"]):
        approx(segs[seg].slope_used, expected)
    for seg in SEGMENTS:
        deltas = [segs[seg].respond(segs[seg].price0 + d)[2] for d in model.DEFAULT_DELTAS]
        for got, exp in zip(deltas, GOLD["whatif_delta"]["|".join(seg)]):
            approx(got, exp, 1e-6)


@pytest.mark.parametrize("city", CITIES)
def test_whatif_grid(data, city):
    segs = _segs(data, model.CASE_GAP_ONLY)
    grid = model.whatif_grid(data, city, "Oct", segs)
    np.testing.assert_allclose(grid.profit.values, np.array(GOLD["grid"][city]), rtol=1e-6)
    best_wd, best_we, best_vs_actual = GOLD["grid_best"][city]
    approx(grid.best_weekday, best_wd)
    approx(grid.best_weekend, best_we)
    approx(grid.best_vs_actual, best_vs_actual, 1e-6)


def test_break_even(data):
    inputs = np.array(GOLD["break_even"]["inputs"], dtype=float)   # rows 97..103, cols B..E
    curve = np.array(GOLD["break_even"]["curve"], dtype=float)
    cols = [("Orlando", "@ Oct prices"), ("Orlando", "@ Jul prices"),
            ("Miami", "@ Oct prices"), ("Miami", "@ Jul prices")]
    for j, (city, label) in enumerate(cols):
        be = model.break_even(data, city, "Oct", "Jul")
        approx(be.cap_weekday, inputs[0, j])
        approx(be.cap_weekend, inputs[1, j])
        approx(be.contrib[label][0], inputs[2, j])
        approx(be.contrib[label][1], inputs[3, j])
        approx(be.fixed_costs, inputs[4, j])
        approx(be.break_even[label], inputs[5, j])
        approx(be.actual_util, inputs[6, j])
        utils = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        np.testing.assert_allclose(be.curve(utils)[label].values, curve[:, j], rtol=1e-6)


def test_unit_economics(data):
    ue = model.unit_economics(data)
    gold = GOLD["unit_economics"]
    cols = ["Revenue", "Variable cost", "Vehicle inventory cost", "Other fixed cost",
            "Pre-tax profit", "Margin"]
    np.testing.assert_allclose(ue[cols].values, np.array(gold, dtype=float), rtol=1e-6)


def test_contribution(data):
    c = model.weekday_weekend_contribution(data)
    gold = np.array(GOLD["contribution"], dtype=float)
    cols = ["Weekday contribution", "Weekend contribution", "Weekend share",
            "Weekday contrib / rental", "Weekend contrib / rental", "Weekend utilization"]
    np.testing.assert_allclose(c[cols].values, gold, rtol=1e-6)
