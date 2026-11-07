"""City / day-period selection and the scope-level performance numbers."""
from __future__ import annotations

import numpy as np
import pytest

from pricing import model
from pricing.config import CITIES, DAYPARTS, SEGMENTS, scope
from pricing.data import SimData
from pricing.store import Store
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture(scope="module")
def data() -> SimData:
    store = Store(Path(__file__).resolve().parents[1] / "data" / "_test_facts.csv")
    store.clear()
    store.add_folder(SAMPLE)
    return SimData(store.facts, store.complete_months())


def test_scope_combinations():
    assert scope("Florida", "Both") == (CITIES, DAYPARTS, SEGMENTS)
    assert scope(None, None) == (CITIES, DAYPARTS, SEGMENTS)
    assert scope("Miami", "Weekend") == (["Miami"], ["Weekend"], [("Miami", "Weekend")])
    assert scope("Orlando", "Both")[2] == [("Orlando", "Weekday"), ("Orlando", "Weekend")]


def test_florida_is_sum_of_cities(data):
    df, label = model.scope_performance(data, CITIES, DAYPARTS)
    assert label == "Pre-tax profit"
    assert np.allclose(df["Florida"], df["Orlando"] + df["Miami"])


def test_single_city_has_no_florida_column(data):
    df, _ = model.scope_performance(data, ["Miami"], DAYPARTS)
    assert list(df.columns) == ["Miami"]


def test_single_daypart_uses_contribution(data):
    df, label = model.scope_performance(data, CITIES, ["Weekend"])
    assert label == "Weekend contribution"
    assert np.allclose(df["Orlando"], data.net("total", "Orlando", "Weekend Contribution"))


def test_combined_bridge_adds_up(data):
    bridges = [model.profit_bridge(data, c, "Sep", "Oct") for c in CITIES]
    fl = model.combine_bridges(bridges)
    assert fl.city == "Florida"
    assert fl.start == pytest.approx(sum(b.start for b in bridges))
    assert fl.end == pytest.approx(sum(b.end for b in bridges))
    drivers = sum(v for _, v in fl.steps[1:-1])
    assert fl.start + drivers == pytest.approx(fl.end)
