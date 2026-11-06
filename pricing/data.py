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
        self.demand_estimated = False
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
        return self.series(f"net_income_{basis}", line, city)

    def rentals(self, city: str, daypart: str) -> pd.Series:
        """Rentals = revenue / price, exactly as the Excel workbook derives them."""
        line = f"Revenue from {daypart} Rentals"
        return self.net("total", city, line) / self.net("prv", city, line)

    # -- demand by day period (optional paste, else estimated) ------------------ #
    def demand(self, city: str, daypart: str) -> pd.Series:
        key = (city, daypart)
        if key in self._demand_cache:
            return self._demand_cache[key]
        s = self.series("demand_by_daypart", "demand", city, daypart)
        if s.isna().any():
            s = s.fillna(self._estimate_demand(city, daypart))   # exact where pasted
            self.demand_estimated = True
        self._demand_cache[key] = s
        return s

    def _estimate_demand(self, city: str, daypart: str) -> pd.Series:
        """Estimate day-period demand when the simulation screen was not pasted.

        demand ~= units sold in that day period + unfilled orders, where unfilled orders are
        assigned to the day period that is at capacity (the busier one if both are).
        Accurate to roughly +/-0.1% because unit sales are rounded to thousands.
        """
        sold = (self.units(city, daypart, "Univ") + self.units(city, daypart, "Comp"))
        unfilled = self.market(city, "unfilled").fillna(0)
        util = {d: self.utilization(city, d) for d in DAYPARTS}
        other = [d for d in DAYPARTS if d != daypart][0]
        mine_full = util[daypart] >= util[other]
        return sold + unfilled.where(mine_full, 0)
