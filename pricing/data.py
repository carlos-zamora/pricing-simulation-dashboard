"""Read-only, analysis-friendly view over the tidy facts."""
from __future__ import annotations

import pandas as pd

from .config import CITIES, DAYPARTS, MONTH_ORDER, REQUIRED_TABLES


class SimData:
    """Accessors that return month-indexed Series. Only complete months are exposed."""

    def __init__(self, facts: pd.DataFrame, months: list[str] | None = None):
        self.facts = facts
        if months is None:
            from .store import Store  # local import to avoid a cycle
            st = Store.__new__(Store)
            st.facts = facts
            months = st.complete_months()
        self.months: list[str] = months
        self._demand_cache: dict[tuple[str, str], pd.Series] = {}

    # -- basics ------------------------------------------------------------- #
    @property
    def first(self) -> str:
        return self.months[0]

    @property
    def latest(self) -> str:
        return self.months[-1]

    def has_table(self, table: str) -> bool:
        return not self.facts[self.facts["table"] == table].empty

    def series(self, table: str, field: str, city: str, daypart: str = "",
               firm: str = "") -> pd.Series:
        f = self.facts
        sel = f[(f["table"] == table) & (f["city"] == city) & (f["field"] == field)
                & (f["daypart"] == daypart) & (f["firm"] == firm)]
        s = sel.set_index("month")["value"]
        return s.reindex(self.months)

    # -- specific series ------------------------------------------------------ #
    def price(self, city: str, daypart: str, firm: str) -> pd.Series:
        return self.series("price", "price", city, daypart, firm)

    def utilization(self, city: str, daypart: str) -> pd.Series:
        return self.series("capacity_utilization", "utilization", city, daypart)

    def orders(self, city: str) -> pd.Series:
        return self.series("capacity_utilization", "orders", city, "Total")

    def market(self, city: str, field: str) -> pd.Series:
        return self.series("market_demand", field, city)

    def units(self, city: str, daypart: str, firm: str) -> pd.Series:
        return self.series("unit_sales", "units", city, daypart, firm)

    def fleet(self, city: str) -> pd.Series:
        return self.series("fleet_size", "fleet_size", city)

    def net(self, basis: str, city: str, line: str) -> pd.Series:
        """A net income line. 'total' comes from the paste; the per-rented-vehicle ('prv') and
        per-vehicle-per-month ('pvpm') views are derived from it, so those screens need not be
        copied. A stored value for a month wins over the derived one."""
        stored = self.series(f"net_income_{basis}", line, city)
        if basis == "prv":
            return stored.combine_first(self._per_rental(city, line))
        if basis == "pvpm":
            return stored.combine_first(self._per_vehicle(city, line))
        return stored

    def rentals(self, city: str, daypart: str) -> pd.Series:
        """Rentals = revenue / price (inherits the simulation's rounding of revenue)."""
        revenue = self.net("total", city, f"Revenue from {daypart} Rentals")
        return revenue / self.price(city, daypart, "Univ")

    def _per_rental(self, city: str, line: str) -> pd.Series:
        """Net income line per rented vehicle: revenue lines are the price, the day-period
        contributions use that day period's rentals, everything else uses all rentals.
        Within about 0.3% of the simulation's own table (its totals are rounded)."""
        for dp in DAYPARTS:
            if line == f"Revenue from {dp} Rentals":
                return self.price(city, dp, "Univ")
            if line == f"{dp} Contribution":
                return self.net("total", city, line) / self.rentals(city, dp)
        all_rentals = sum(self.rentals(city, dp) for dp in DAYPARTS)
        return self.net("total", city, line) / all_rentals

    def _per_vehicle(self, city: str, line: str) -> pd.Series:
        """Net income line per vehicle per month = total / fleet. The fleet is fixed during the
        simulation, so the last known fleet size carries over to months not yet pasted."""
        return self.net("total", city, line) / self.fleet(city).ffill().bfill()


    # -- demand by day period ---------------------------------------------------- #
    def demand(self, city: str, daypart: str) -> pd.Series:
        """Orders demanded in a day period = units sold + unfilled orders.

        The simulation reports unfilled orders for the whole city, so they are assigned to the
        day period that is more utilised (the one that ran out of cars; if both are equally
        full, the weekday). Unit sales are rounded to thousands, so expect roughly +/-0.5%.
        """
        key = (city, daypart)
        if key not in self._demand_cache:
            sold = self.units(city, daypart, "Univ") + self.units(city, daypart, "Comp")
            unfilled = self.market(city, "unfilled").fillna(0)
            other = [d for d in DAYPARTS if d != daypart][0]
            at_capacity = self.utilization(city, daypart) >= self.utilization(city, other)
            self._demand_cache[key] = sold + unfilled.where(at_capacity, 0)
        return self._demand_cache[key]
