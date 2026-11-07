"""The per-rented-vehicle and per-vehicle-per-month net income screens are derived, not pasted."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pricing import model
from pricing.config import CITIES, NET_INCOME_LINES, REQUIRED_TABLES
from pricing.data import SimData
from pricing.store import Store

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ("net_income_prv", "net_income_pvpm")


@pytest.fixture(scope="module")
def full():
    store = Store(ROOT / "data" / "_test_facts.csv")
    store.clear()
    store.add_folder(ROOT / "sample_data")
    return store.facts.copy()


def _lean(full: pd.DataFrame, drop=DERIVED) -> pd.DataFrame:
    return full[~full["table"].isin(drop)].reset_index(drop=True)


def test_only_seven_screens_are_required():
    assert "net_income_prv" not in REQUIRED_TABLES
    assert set(REQUIRED_TABLES) == {"price", "unit_sales", "market_demand",
                                    "capacity_utilization", "fleet_size", "net_income_total"}


@pytest.mark.parametrize("city", CITIES)
@pytest.mark.parametrize("line", NET_INCOME_LINES)
def test_per_rented_vehicle_matches_the_real_screen(full, city, line):
    real = SimData(full).net("prv", city, line)
    derived = SimData(_lean(full)).net("prv", city, line)
    # The simulation rounds its totals to 3 significant figures: expect cents, not dollars.
    assert (derived - real).abs().max() < 0.06


@pytest.mark.parametrize("city", CITIES)
@pytest.mark.parametrize("line", NET_INCOME_LINES)
def test_per_vehicle_matches_the_real_screen(full, city, line):
    real = SimData(full).net("pvpm", city, line)
    derived = SimData(_lean(full)).net("pvpm", city, line)
    tol = 0.01 * real.abs().max()                       # the real screen is itself rounded
    assert (derived - real).abs().max() <= max(tol, 1e-9)


def test_rentals_do_not_depend_on_the_derived_screens(full):
    a, b = SimData(full), SimData(_lean(full))
    for city in CITIES:
        for dp in ("Weekday", "Weekend"):
            assert a.rentals(city, dp).equals(b.rentals(city, dp))


def test_recommendations_are_the_same_without_the_derived_screens(full):
    def guides(facts):
        data = SimData(facts)
        pvu, dvu = model.price_vs_util(data), model.demand_vs_util(data)
        segs = {c: model.whatif_segments(data, data.latest, c, pvu, dvu) for c in model.CASES}
        return {c: model.price_guide(data, c, data.latest, segs) for c in CITIES}

    a, b = guides(full), guides(_lean(full))
    for city in CITIES:
        assert (a[city].pick_weekday, a[city].pick_weekend) == \
               (b[city].pick_weekday, b[city].pick_weekend)
        assert (a[city].is_hold, a[city].held) == (b[city].is_hold, b[city].held)
        assert a[city].worst.best_vs_actual == pytest.approx(b[city].worst.best_vs_actual,
                                                             rel=0.02, abs=1)


def test_a_new_month_needs_only_the_required_screens(full):
    """November arrives without prv / pvpm: it must still be analysed."""
    nov = full[(full["month"] == "Oct") & ~full["table"].isin(DERIVED)]
    facts = pd.concat([full, nov.assign(month="Nov")], ignore_index=True)
    store = Store(ROOT / "data" / "_test_facts.csv")
    store.facts = facts
    assert store.complete_months()[-1] == "Nov"
    data = SimData(store.facts)
    assert data.net("prv", "Miami", "Variable Costs")["Nov"] == pytest.approx(18.0, abs=0.05)
    assert data.net("pvpm", "Orlando", "Total Revenue")["Nov"] > 0       # fleet size pasted
    assert len(model.unit_economics(data)) == 2 * len(data.months)
    assert model.break_even(data, "Orlando", "Nov", "Oct").break_even


def test_stored_screens_still_win_over_derived(full):
    data = SimData(full)
    real = data.series("net_income_prv", "Variable Costs", "Miami")
    assert data.net("prv", "Miami", "Variable Costs").equals(real)
