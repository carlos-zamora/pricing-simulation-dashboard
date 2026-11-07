"""Adding a new month must flow through to the analysis with no code or formula edits."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from pricing import charts, model
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


def test_month_missing_unit_sales_is_not_analysed(tmp_path):
    store = _with_november(tmp_path, drop_tables=("unit_sales",))
    assert "Nov" in store.months() and "Nov" not in store.complete_months()


def test_demand_is_units_plus_unfilled(tmp_path):
    store = Store(tmp_path / "f.csv")
    store.add_folder(ROOT / "sample_data")
    data = SimData(store.facts)
    # Miami Oct: weekday ran out of cars, so the 64K unfilled orders land on the weekday.
    assert data.demand("Miami", "Weekday")["Oct"] == 600_000 + 64_000
    assert data.demand("Miami", "Weekend")["Oct"] == 96_000
    assert data.demand("Orlando", "Weekday")["Jul"] == 800_000


def test_legacy_day_period_rows_are_ignored_on_load(tmp_path):
    store = Store(tmp_path / "f.csv")
    store.add_folder(ROOT / "sample_data")
    legacy = store.facts.iloc[:3].copy()
    legacy["table"] = "demand_by_daypart"
    pd.concat([store.facts, legacy]).to_csv(tmp_path / "f.csv", index=False)
    assert "demand_by_daypart" not in set(Store(tmp_path / "f.csv").facts["table"])


def test_best_fit_legend_states_slope(tmp_path):
    store = Store(tmp_path / "f.csv")
    store.add_folder(ROOT / "sample_data")
    data = SimData(store.facts)
    pvu = model.price_vs_util(data)
    p = pvu[("Orlando", "Weekday")]
    names = [t.name for t in charts.util_vs_gap(p).data]
    assert any(n and "slope -3.80 util pts per +$1 gap" in n and "R² 0.90" in n and "<br>" in n
               for n in names), names
    # A segment whose price gap never changed still gets an honest legend entry.
    flat = pvu[("Miami", "Weekend")]
    assert any(n and "n/a" in n for n in [t.name for t in charts.util_vs_gap(flat).data])
    dvu = model.demand_vs_util(data)[("Orlando", "Weekday")]
    assert any(n and "util pts per 10K orders" in n for n in [t.name for t in charts.util_vs_demand(dvu).data])
    assert any(n and "util pts per +$1 gap" in n for n in [t.name for t in charts.price_effect_after_demand(dvu).data])
