"""Adding a new month must flow through to the analysis with no code or formula edits."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pricing import model
from pricing.data import SimData
from pricing.store import Store

ROOT = Path(__file__).resolve().parents[1]


def _with_november(tmp_path, drop_tables=()):
    store = Store(tmp_path / "f.csv")
    store.add_folder(ROOT / "sample_data")
    oct_rows = store.facts[(store.facts["month"] == "Oct")
                           & ~store.facts["table"].isin(drop_tables)].copy()
    nov = oct_rows.assign(month="Nov")
    nov.loc[(nov["table"] == "price") & (nov["city"] == "Orlando")
            & (nov["daypart"] == "Weekday") & (nov["firm"] == "Univ"), "value"] = 43.0
    store.facts = pd.concat([store.facts, nov], ignore_index=True)
    return store


def test_november_flows_through(tmp_path):
    store = _with_november(tmp_path)
    assert store.complete_months() == ["Jul", "Aug", "Sep", "Oct", "Nov"]
    data = SimData(store.facts)
    pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
    assert len(pvu[("Orlando", "Weekday")].table) == 5
    segs = model.whatif_segments(data, "Nov", model.CASE_GAP_ONLY, pvu, dvu)
    assert model.whatif_grid(data, "Orlando", "Nov", segs).profit.shape == (7, 7)
    assert model.profit_bridge(data, "Miami", "Jul", "Nov").steps[-1][0] == "Nov profit"
    assert model.break_even(data, "Orlando", "Nov", "Jul").break_even


def test_missing_day_period_screen_falls_back_to_estimate(tmp_path):
    store = _with_november(tmp_path)
    nov_dd = (store.facts["table"] == "demand_by_daypart") & (store.facts["month"] == "Nov")
    store.facts = store.facts[~nov_dd]
    data = SimData(store.facts)
    assert "Nov" in data.months
    d = data.demand("Orlando", "Weekday")
    assert not d.isna().any() and data.demand_estimated
    # months that were pasted keep their exact values
    assert d["Jul"] == 799878


def test_month_without_any_demand_source_is_not_analysed(tmp_path):
    store = _with_november(tmp_path, drop_tables=("demand_by_daypart", "unit_sales"))
    assert "Nov" not in store.complete_months()
