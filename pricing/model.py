"""The pricing analysis: regressions, profit bridge, what-if, break-even, unit economics.

Slopes are in *utilization points* (percentage points) per $1 unless stated otherwise.
Everything takes a SimData and returns plain dataclasses/DataFrames, so it is testable
without the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import CITIES, DAYPARTS, MONTH_ORDER, SEGMENTS
from .data import SimData

CASE_GAP_ONLY = "Gap-only (upper bound)"
CASE_DEMAND_ADJ = "Demand-adjusted (lower bound)"
CASES = [CASE_GAP_ONLY, CASE_DEMAND_ADJ]
CASE_LABELS = {CASE_GAP_ONLY: "Cautious", CASE_DEMAND_ADJ: "Optimistic"}


# --------------------------------------------------------------------------- #
# Regression helpers (ordinary least squares; None when a slope is undefined)
# --------------------------------------------------------------------------- #
@dataclass
class Fit:
    slope: float | None
    intercept: float | None
    r2: float | None

    def predict(self, x):
        x = np.asarray(x, dtype=float)
        if self.slope is None:
            return np.full_like(x, np.nan)
        return self.intercept + self.slope * x


def linfit(x, y) -> Fit:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2:
        return Fit(None, None, None)
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    syy = ((y - ym) ** 2).sum()
    sxy = ((x - xm) * (y - ym)).sum()
    if sxx < 1e-12:
        return Fit(None, None, None)
    slope = sxy / sxx
    r2 = sxy ** 2 / (sxx * syy) if syy > 1e-12 else None
    return Fit(slope, ym - slope * xm, r2)


# --------------------------------------------------------------------------- #
# Price vs utilization
# --------------------------------------------------------------------------- #
@dataclass
class PriceVsUtil:
    city: str
    daypart: str
    table: pd.DataFrame            # index month; univ, comp, gap, util
    slope_pts: float | None        # util points per +$1 of (Univ - Comp) gap
    r2: float | None

    @property
    def name(self) -> str:
        return f"{self.city} – {self.daypart}"


def price_vs_util(data: SimData) -> dict[tuple[str, str], PriceVsUtil]:
    out = {}
    for city, dp in SEGMENTS:
        t = pd.DataFrame({
            "univ": data.price(city, dp, "Univ"),
            "comp": data.price(city, dp, "Comp"),
            "util": data.utilization(city, dp),
        })
        t["gap"] = t["univ"] - t["comp"]
        fit = linfit(t["gap"], t["util"])
        out[(city, dp)] = PriceVsUtil(city, dp, t, None if fit.slope is None else fit.slope * 100,
                                      fit.r2)
    return out


# --------------------------------------------------------------------------- #
# Demand vs utilization
# --------------------------------------------------------------------------- #
@dataclass
class DemandVsUtil:
    city: str
    daypart: str
    table: pd.DataFrame            # demand, univ, comp, gap, util, predicted, residual, idx_*
    r2_demand: float | None
    demand_slope_pts_per_10k: float | None
    price_slope_pts: float | None  # util pts per +$1 gap AFTER removing demand

    @property
    def name(self) -> str:
        return f"{self.city} – {self.daypart}"


def demand_vs_util(data: SimData) -> dict[tuple[str, str], DemandVsUtil]:
    out = {}
    for city, dp in SEGMENTS:
        t = pd.DataFrame({
            "demand": data.demand(city, dp),
            "univ": data.price(city, dp, "Univ"),
            "comp": data.price(city, dp, "Comp"),
            "util": data.utilization(city, dp),
        })
        t["gap"] = t["univ"] - t["comp"]
        dfit = linfit(t["demand"], t["util"])
        t["predicted"] = dfit.predict(t["demand"]) if dfit.slope is not None else t["util"].mean()
        t["residual"] = t["util"] - t["predicted"]
        pfit = linfit(t["gap"], t["residual"])
        for col, src in (("idx_demand", "demand"), ("idx_univ", "univ"),
                         ("idx_comp", "comp"), ("idx_util", "util")):
            t[col] = t[src] / t[src].iloc[0] * 100
        out[(city, dp)] = DemandVsUtil(
            city, dp, t, dfit.r2,
            None if dfit.slope is None else dfit.slope * 10000 * 100,
            None if pfit.slope is None else pfit.slope * 100)
    return out


# --------------------------------------------------------------------------- #
# Price vs pre-tax profit
# --------------------------------------------------------------------------- #
def price_vs_profit(data: SimData, city: str) -> pd.DataFrame:
    cols = {}
    for dp in DAYPARTS:
        cols[f"{dp} price"] = data.price(city, dp, "Univ")
        cols[f"{dp} comp price"] = data.price(city, dp, "Comp")
        cols[f"{dp} utilization"] = data.utilization(city, dp)
    cols["Pre-tax profit"] = data.net("total", city, "Pre-Tax Profit")
    cols["Unfilled orders"] = data.market(city, "unfilled")
    cols["Unfilled share"] = cols["Unfilled orders"] / data.market(city, "demand")
    cols["Fleet size"] = data.fleet(city)
    return pd.DataFrame(cols)


# --------------------------------------------------------------------------- #
# Profit bridge: base month -> compare month
# --------------------------------------------------------------------------- #
@dataclass
class Bridge:
    city: str
    base: str
    compare: str
    steps: list[tuple[str, float]]     # label, signed value (first/last are totals)
    inputs: dict[str, float]

    @property
    def start(self) -> float:
        return self.steps[0][1]

    @property
    def end(self) -> float:
        return self.steps[-1][1]


def profit_bridge(data: SimData, city: str, base: str, compare: str) -> Bridge:
    price = {dp: data.net("prv", city, f"Revenue from {dp} Rentals") for dp in DAYPARTS}
    rent = {dp: data.rentals(city, dp) for dp in DAYPARTS}
    contrib0 = {dp: data.net("prv", city, f"{dp} Contribution")[base] for dp in DAYPARTS}
    tot = lambda line: data.net("total", city, line)
    vc = data.net("prv", city, "Variable Costs")

    price_eff = sum((price[dp][compare] - price[dp][base]) * rent[dp][compare] for dp in DAYPARTS)
    volume_eff = sum((rent[dp][compare] - rent[dp][base]) * contrib0[dp] for dp in DAYPARTS)
    vc_eff = -(vc[compare] - vc[base]) * sum(rent[dp][compare] for dp in DAYPARTS)
    fixed = lambda m: tot("Vehicle Inventory Costs")[m] + tot("Other Fixed Costs")[m]
    fixed_eff = -(fixed(compare) - fixed(base))
    p0, p1 = tot("Pre-Tax Profit")[base], tot("Pre-Tax Profit")[compare]
    rounding = p1 - (p0 + price_eff + volume_eff + vc_eff + fixed_eff)
    steps = [(f"{base} profit", p0), ("Price effect", price_eff), ("Volume effect", volume_eff),
             ("Variable cost / rental", vc_eff), ("Fixed costs", fixed_eff),
             ("Rounding in source", rounding), (f"{compare} profit", p1)]
    return Bridge(city, base, compare, steps, {})


def combine_bridges(bridges: list[Bridge], name: str = "Florida") -> Bridge:
    """Add city bridges step by step (every step is a dollar amount, so they are additive)."""
    first = bridges[0]
    steps = [(label, sum(b.steps[i][1] for b in bridges)) for i, (label, _) in enumerate(first.steps)]
    return Bridge(name, first.base, first.compare, steps, {})


def scope_performance(data: SimData, cities: list[str],
                      dayparts: list[str]) -> tuple[pd.DataFrame, str]:
    """Monthly profit for each selected city, plus a Florida total when there are several.

    Both day periods: pre-tax profit. One day period: that period's contribution (the
    simulation reports pre-tax profit only for a whole city). Returns (table, measure name).
    """
    if len(dayparts) == len(DAYPARTS):
        label = "Pre-tax profit"
        cols = {c: data.net("total", c, "Pre-Tax Profit") for c in cities}
    else:
        label = f"{dayparts[0]} contribution"
        cols = {c: data.net("total", c, f"{dayparts[0]} Contribution") for c in cities}
    df = pd.DataFrame(cols)
    if len(cities) > 1:
        df["Florida"] = df.sum(axis=1)
    return df, label


# --------------------------------------------------------------------------- #
# What-if: pre-tax profit by price (built on the focus month's prices & volumes)
# --------------------------------------------------------------------------- #
@dataclass
class WhatIfSegment:
    city: str
    daypart: str
    price0: float
    rentals0: float
    util0: float
    var_cost: float
    slope_demand_adj: float | None
    slope_gap_only: float | None
    slope_used: float = 0.0
    fleet0: float | None = None          # the city's fleet (capacity) last month
    unfilled0: float = 0.0               # our share of last month's unfilled orders in this period
    inventory_per_vehicle: float = 0.0   # monthly vehicle inventory cost per vehicle (city level)

    @property
    def name(self) -> str:
        return f"{self.city} – {self.daypart}"

    def respond(self, new_price: float, new_fleet: float | None = None
                ) -> tuple[float, float, float]:
        """(utilization, rentals, change in profit vs the month's actual).

        Price moves demand (utilization slope). A different fleet changes how much of that demand
        can be served: rentals = min(demand, capacity), utilization = rentals / capacity. At full
        capacity last month, our share of the unfilled orders counts as extra demand. Vehicle
        inventory cost is charged per vehicle added or removed (split between day periods by the
        caller, see `scenario_profit`)."""
        util_p = max(0.0, self.util0 + self.slope_used / 100 * (new_price - self.price0))
        if not self.util0:
            rentals, util = self.rentals0, 0.0
        else:
            cap0 = self.rentals0 / self.util0               # rentals servable at 100% last month
            fleet = new_fleet if (new_fleet and self.fleet0) else self.fleet0
            cap = cap0 * fleet / self.fleet0 if self.fleet0 else cap0
            demand = self.rentals0 * util_p / self.util0
            if self.util0 >= 0.99:
                demand += self.unfilled0 * util_p / self.util0
            rentals = min(demand, cap)
            util = rentals / cap if cap else 0.0
        delta = ((new_price - self.var_cost) * rentals
                 - (self.price0 - self.var_cost) * self.rentals0)
        return util, rentals, delta


def _num(v) -> float | None:
    return None if pd.isna(v) else float(v)


def _our_unfilled(data: SimData, city: str, dp: str, month: str) -> float:
    """Our share (by unit sales) of the unfilled orders assigned to this day period."""
    ours, comp = data.units(city, dp, "Univ")[month], data.units(city, dp, "Comp")[month]
    unfilled = data.demand(city, dp)[month] - ours - comp
    return float(unfilled * ours / (ours + comp)) if ours + comp > 0 and unfilled > 0 else 0.0


def _inventory_per_vehicle(data: SimData, city: str, month: str) -> float:
    fleet = data.fleet(city)[month]
    cost = data.net("total", city, "Vehicle Inventory Costs")[month]
    return 0.0 if pd.isna(fleet) or not fleet else float(cost / fleet)


def whatif_segments(data: SimData, month: str, case: str,
                    pvu: dict, dvu: dict) -> dict[tuple[str, str], WhatIfSegment]:
    out = {}
    for city, dp in SEGMENTS:
        seg = WhatIfSegment(
            city, dp,
            price0=data.net("prv", city, f"Revenue from {dp} Rentals")[month],
            rentals0=data.rentals(city, dp)[month],
            util0=data.utilization(city, dp)[month],
            var_cost=data.net("prv", city, "Variable Costs")[month],
            slope_demand_adj=dvu[(city, dp)].price_slope_pts,
            slope_gap_only=pvu[(city, dp)].slope_pts,
            fleet0=_num(data.fleet(city)[month]),
            unfilled0=_our_unfilled(data, city, dp, month),
            inventory_per_vehicle=_inventory_per_vehicle(data, city, month))
        chosen = seg.slope_gap_only if case == CASE_GAP_ONLY else seg.slope_demand_adj
        # Capped at 0: no measured benefit from raising price; 0 where unmeasurable.
        seg.slope_used = 0.0 if chosen is None else min(0.0, chosen)
        out[(city, dp)] = seg
    return out


@dataclass
class SegmentStatus:
    """Last month's numbers for one city x day period (the always-visible status strip)."""
    city: str
    daypart: str
    utilization: float
    utilization_prev: float
    capacity: float | None          # city fleet size (shared by both day periods)
    capacity_prev: float | None
    price: float
    price_prev: float
    comp_price: float
    slope_cautious: float | None    # util points per +$1; None = unmeasurable
    slope_optimistic: float | None
    contribution: float             # day-period contribution (pre-tax is only per city)
    contribution_prev: float

    @property
    def elasticity_range(self) -> tuple[float, float] | None:
        """(low, high) of the utilization-points-per-+$1 slope across the two assumptions,
        each capped at 0. None when price sensitivity can't be measured."""
        if self.slope_cautious is None or self.slope_cautious >= 0:
            return None
        vals = [min(0.0, v) for v in (self.slope_cautious, self.slope_optimistic) if v is not None]
        return min(vals), max(vals)

    @property
    def gap(self) -> float:
        return self.price - self.comp_price

    @property
    def at_capacity(self) -> bool:
        return self.utilization >= 0.99


@dataclass
class Status:
    month: str
    segments: dict[tuple[str, str], SegmentStatus]
    city_profit: dict[str, float]      # each city's profit/loss in `month` (change in accumulated profit)
    florida_profit: float
    florida_delta: float               # profit/loss vs the previous month's profit/loss
    florida_cumulative: float | None   # the simulation's accumulated pre-tax profit; None if missing
    since: str | None                  # first month with a profit/loss (None = none played yet)


def played_months(data: SimData) -> list[str]:
    """Months in which the game was really played: the simulation's accumulated pre-tax profit
    (summed over both cities) moved. It reads $0 until the first month is played, so the
    starting position and the bundled sample never count as profit or loss."""
    acc = _accumulated(data).fillna(0.0).sum(axis=1)
    change = acc.diff().fillna(acc)               # first month compares with $0
    return [m for m in data.months if abs(change[m]) > 0.5]


def _accumulated(data: SimData) -> pd.DataFrame:
    return pd.DataFrame({c: data.net("total", c, "Accumulated Pre-Tax Profit") for c in CITIES})


def status_snapshot(data: SimData, month: str, prev: str, segs_by_case: dict,
                    played: list[str] | None = None) -> Status:
    """Profit and loss comes from the simulation's own accumulated pre-tax profit: a month's
    profit/loss is the change in it, the total is its latest value. `played`: months that really
    were played (default `played_months`); contributions of other months show as $0."""
    played_set = set(played_months(data) if played is None else played)

    def contribution(city: str, dp: str, m: str) -> float:
        return float(data.net("total", city, f"{dp} Contribution")[m]) if m in played_set else 0.0

    def num(v) -> float | None:
        return None if pd.isna(v) else float(v)

    segments = {}
    for city, dp in SEGMENTS:
        cautious = segs_by_case[CASE_GAP_ONLY][(city, dp)]
        optimistic = segs_by_case[CASE_DEMAND_ADJ][(city, dp)]
        fleet = data.fleet(city)
        util = data.utilization(city, dp)
        price = data.price(city, dp, "Univ")
        now = contribution(city, dp, month)
        segments[(city, dp)] = SegmentStatus(
            city, dp, float(util[month]), float(util[prev]),
            num(fleet[month]), num(fleet[prev]),
            float(price[month]), float(price[prev]),
            float(data.price(city, dp, "Comp")[month]),
            cautious.slope_gap_only, optimistic.slope_demand_adj,
            now, contribution(city, dp, prev))
    acc = _accumulated(data)
    change = acc.diff().fillna(acc).fillna(0.0)       # profit/loss per month, per city
    florida = change.sum(axis=1)
    total = acc.loc[month]
    pl = [m for m in data.months if m in played_set]
    return Status(month, segments, {c: float(change[c][month]) for c in CITIES},
                  float(florida[month]), float(florida[month]) - float(florida[prev]),
                  None if total.isna().any() else float(total.sum()), pl[0] if pl else None)


DEFAULT_DELTAS = [-6, -4, -2, 0, 2, 4, 6]


@dataclass
class WhatIfGrid:
    city: str
    deltas: list[int]
    weekday_prices: list[float]
    weekend_prices: list[float]
    profit: pd.DataFrame           # rows = weekday price, cols = weekend price
    base_profit: float
    best_weekday: float
    best_weekend: float
    best_profit: float

    @property
    def best_vs_actual(self) -> float:
        return self.best_profit - self.base_profit


def whatif_grid(data: SimData, city: str, month: str,
                segs: dict, deltas: list[int] | None = None) -> WhatIfGrid:
    deltas = deltas or DEFAULT_DELTAS
    wd, we = segs[(city, "Weekday")], segs[(city, "Weekend")]
    base_profit = data.net("total", city, "Pre-Tax Profit")[month]
    wd_prices = [wd.price0 + d for d in deltas]
    we_prices = [we.price0 + d for d in deltas]
    d_wd = [wd.respond(p)[2] for p in wd_prices]
    d_we = [we.respond(p)[2] for p in we_prices]
    grid = pd.DataFrame([[base_profit + a + b for b in d_we] for a in d_wd],
                        index=wd_prices, columns=we_prices)
    flat = int(np.argmax(grid.values))            # first max, row-major
    r, c = divmod(flat, grid.shape[1])
    return WhatIfGrid(city, list(deltas), wd_prices, we_prices, grid, base_profit,
                      wd_prices[r], we_prices[c], float(grid.values[r, c]))


@dataclass
class PriceGuide:
    """Both sensitivity assumptions side by side, and the price pair that holds up under both."""
    city: str
    cautious: WhatIfGrid           # utilization falls fastest when price rises (gap-only slope)
    optimistic: WhatIfGrid         # utilization falls slowest (demand-adjusted slope)
    worst: WhatIfGrid              # cell-by-cell worse of the two; its best cell is the pick
    measurable: dict[str, bool]    # daypart -> is there evidence that price moves utilization?

    @property
    def pick_weekday(self) -> float:
        return self.worst.best_weekday

    @property
    def pick_weekend(self) -> float:
        return self.worst.best_weekend

    def _delta(self, grid: WhatIfGrid) -> float:
        return float(grid.profit.loc[self.pick_weekday, self.pick_weekend]) - grid.base_profit

    @property
    def cautious_delta(self) -> float:
        return self._delta(self.cautious)

    @property
    def optimistic_delta(self) -> float:
        return self._delta(self.optimistic)

    @property
    def is_hold(self) -> bool:
        """True when no price change beats the current prices in the worst case."""
        return abs(self.worst.best_vs_actual) < 1

    @property
    def held(self) -> list[str]:
        """Day periods whose price is held because its sensitivity can't be measured."""
        return [dp for dp, ok in self.measurable.items() if not ok]

    @property
    def on_edge(self) -> bool:
        w = self.worst
        return (self.pick_weekday in (w.weekday_prices[0], w.weekday_prices[-1])
                or self.pick_weekend in (w.weekend_prices[0], w.weekend_prices[-1]))


def price_guide(data: SimData, city: str, month: str,
                segs_by_case: dict[str, dict], deltas: list[int] | None = None) -> PriceGuide:
    """Suggest the price pair with the best worst-case profit across both assumptions.

    A day period only moves if the data show price matters there (cautious slope < 0). Where it
    is unmeasurable (price gap never changed, or utilization pinned at capacity so the slope has
    the wrong sign) both assumptions treat price as free, which would suggest unlimited
    increases, so that price is held at its current level and its grid cells are left blank.
    """
    cautious = whatif_grid(data, city, month, segs_by_case[CASE_GAP_ONLY], deltas)
    optimistic = whatif_grid(data, city, month, segs_by_case[CASE_DEMAND_ADJ], deltas)
    n, mid = len(cautious.deltas), cautious.deltas.index(0)
    measurable = {dp: segs_by_case[CASE_GAP_ONLY][(city, dp)].slope_used < 0 for dp in DAYPARTS}
    rows = range(n) if measurable["Weekday"] else [mid]
    cols = range(n) if measurable["Weekend"] else [mid]
    allowed = np.zeros((n, n), dtype=bool)
    allowed[np.ix_(rows, cols)] = True
    worst_profit = np.where(allowed, np.minimum(cautious.profit.values, optimistic.profit.values),
                            np.nan)
    r, c = divmod(int(np.nanargmax(worst_profit)), n)
    worst = WhatIfGrid(city, cautious.deltas, cautious.weekday_prices, cautious.weekend_prices,
                       pd.DataFrame(worst_profit, index=cautious.profit.index,
                                    columns=cautious.profit.columns),
                       cautious.base_profit, cautious.weekday_prices[r],
                       cautious.weekend_prices[c], float(worst_profit[r, c]))
    return PriceGuide(city, cautious, optimistic, worst, measurable)


def whatif_curve(seg: WhatIfSegment, deltas: list[int] | None = None) -> pd.DataFrame:
    deltas = deltas or DEFAULT_DELTAS
    rows = []
    for d in deltas:
        util, rentals, delta = seg.respond(seg.price0 + d)
        rows.append(dict(delta=d, price=seg.price0 + d, utilization=util,
                         rentals=rentals, delta_profit=delta))
    return pd.DataFrame(rows)


def scenario_profit(data: SimData, month: str, segs: dict, prices: dict,
                    fleets: dict[str, float] | None = None) -> dict:
    """Project a custom price for each of the four segments and a fleet size per city (the live
    meeting tool). Changing the fleet also changes vehicle inventory costs, charged to the city."""
    out = {}
    for city in CITIES:
        total = data.net("total", city, "Pre-Tax Profit")[month]
        fleet0 = segs[(city, DAYPARTS[0])].fleet0
        fleet = (fleets or {}).get(city) or fleet0
        detail = {}
        for dp in DAYPARTS:
            util, rentals, delta = segs[(city, dp)].respond(prices[(city, dp)], fleet)
            detail[dp] = dict(utilization=util, rentals=rentals, delta=delta)
            total += delta
        if fleet0 and fleet != fleet0:
            total -= (fleet - fleet0) * segs[(city, DAYPARTS[0])].inventory_per_vehicle
        out[city] = dict(profit=total, detail=detail,
                         actual=data.net("total", city, "Pre-Tax Profit")[month])
    return out


# --------------------------------------------------------------------------- #
# Break-even utilization
# --------------------------------------------------------------------------- #
@dataclass
class BreakEven:
    city: str
    month: str
    base: str
    cap_weekday: float
    cap_weekend: float
    fixed_costs: float
    contrib: dict[str, tuple[float, float]]     # label -> (weekday, weekend) per rental
    break_even: dict[str, float]                # label -> utilization
    actual_util: float

    def curve(self, utils=None) -> pd.DataFrame:
        utils = np.linspace(0.4, 1.0, 13) if utils is None else utils
        return pd.DataFrame({
            label: [u * (self.cap_weekday * c[0] + self.cap_weekend * c[1]) - self.fixed_costs
                    for u in utils] for label, c in self.contrib.items()
        }, index=pd.Index(utils, name="utilization"))


def break_even(data: SimData, city: str, month: str, base: str) -> BreakEven:
    rent_wd, rent_we = data.rentals(city, "Weekday")[month], data.rentals(city, "Weekend")[month]
    cap_wd = rent_wd / data.utilization(city, "Weekday")[month]
    cap_we = rent_we / data.utilization(city, "Weekend")[month]
    fixed = (data.net("total", city, "Vehicle Inventory Costs")[month]
             + data.net("total", city, "Other Fixed Costs")[month])
    contrib = {}
    for label, m in ((f"@ {month} prices", month), (f"@ {base} prices", base)):
        contrib[label] = (data.net("prv", city, "Weekday Contribution")[m],
                          data.net("prv", city, "Weekend Contribution")[m])
    be = {label: fixed / (cap_wd * c[0] + cap_we * c[1]) for label, c in contrib.items()}
    return BreakEven(city, month, base, cap_wd, cap_we, fixed, contrib, be,
                     (rent_wd + rent_we) / (cap_wd + cap_we))


# --------------------------------------------------------------------------- #
# Unit economics & weekday vs weekend contribution
# --------------------------------------------------------------------------- #
def unit_economics(data: SimData) -> pd.DataFrame:
    rows = []
    for city in CITIES:
        for m in data.months:
            g = lambda line: data.net("pvpm", city, line)[m]
            rev = g("Total Revenue")
            rows.append({"label": f"{city} {m}", "city": city, "month": m, "Revenue": rev,
                         "Variable cost": g("Variable Costs"),
                         "Vehicle inventory cost": g("Vehicle Inventory Costs"),
                         "Other fixed cost": g("Other Fixed Costs"),
                         "Pre-tax profit": g("Pre-Tax Profit"),
                         "Margin": g("Pre-Tax Profit") / rev})
    return pd.DataFrame(rows)


def weekday_weekend_contribution(data: SimData) -> pd.DataFrame:
    rows = []
    for city in CITIES:
        for m in data.months:
            wd = data.net("total", city, "Weekday Contribution")[m]
            we = data.net("total", city, "Weekend Contribution")[m]
            rows.append({"label": f"{city} {m}", "city": city, "month": m,
                         "Weekday contribution": wd, "Weekend contribution": we,
                         "Weekend share": we / (wd + we),
                         "Weekday contrib / rental": data.net("prv", city, "Weekday Contribution")[m],
                         "Weekend contrib / rental": data.net("prv", city, "Weekend Contribution")[m],
                         "Weekend utilization": data.utilization(city, "Weekend")[m]})
    return pd.DataFrame(rows)
