"""The analysis, ported 1:1 from the Excel workbook (parity first).

Section numbers refer to the sheets in reference/Pricing_Simulation_Analysis.xlsx.
Slopes are in *utilization points* (percentage points), like the workbook.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import CITIES, DAYPARTS, SEGMENTS
from .data import SimData

CASE_GAP_ONLY = "Gap-only (upper bound)"
CASE_DEMAND_ADJ = "Demand-adjusted (lower bound)"
CASES = [CASE_GAP_ONLY, CASE_DEMAND_ADJ]


# --------------------------------------------------------------------------- #
# Regression helpers (match Excel SLOPE / RSQ / TREND, incl. #DIV/0 -> None)
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
# Sheet "Price vs Util"
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
# Sheet "Demand vs Util"
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
# Sheet "Profit Analysis" §1  price vs pre-tax profit
# --------------------------------------------------------------------------- #
def price_vs_profit(data: SimData, city: str) -> pd.DataFrame:
    return pd.DataFrame({
        "Weekday price": data.net("prv", city, "Revenue from Weekday Rentals"),
        "Weekend price": data.net("prv", city, "Revenue from Weekend Rentals"),
        "Pre-tax profit": data.net("total", city, "Pre-Tax Profit"),
    })


# --------------------------------------------------------------------------- #
# §2  profit bridge  base month -> compare month
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


# --------------------------------------------------------------------------- #
# §3  what-if: pre-tax profit by price (month-of-interest prices & volumes)
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

    @property
    def name(self) -> str:
        return f"{self.city} – {self.daypart}"

    def respond(self, new_price: float) -> tuple[float, float, float]:
        """(utilization, rentals, change in profit vs the month's actual)."""
        util = max(0.0, min(1.0, self.util0 + self.slope_used / 100 * (new_price - self.price0)))
        rentals = self.rentals0 * util / self.util0 if self.util0 else self.rentals0
        delta = ((new_price - self.var_cost) * rentals
                 - (self.price0 - self.var_cost) * self.rentals0)
        return util, rentals, delta


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
            slope_gap_only=pvu[(city, dp)].slope_pts)
        chosen = seg.slope_gap_only if case == CASE_GAP_ONLY else seg.slope_demand_adj
        # Capped at 0: no measured benefit from raising price; 0 where unmeasurable.
        seg.slope_used = 0.0 if chosen is None else min(0.0, chosen)
        out[(city, dp)] = seg
    return out


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
    flat = int(np.argmax(grid.values))            # first max, row-major, like the workbook
    r, c = divmod(flat, grid.shape[1])
    return WhatIfGrid(city, list(deltas), wd_prices, we_prices, grid, base_profit,
                      wd_prices[r], we_prices[c], float(grid.values[r, c]))


def whatif_curve(seg: WhatIfSegment, deltas: list[int] | None = None) -> pd.DataFrame:
    deltas = deltas or DEFAULT_DELTAS
    rows = []
    for d in deltas:
        util, rentals, delta = seg.respond(seg.price0 + d)
        rows.append(dict(delta=d, price=seg.price0 + d, utilization=util,
                         rentals=rentals, delta_profit=delta))
    return pd.DataFrame(rows)


def scenario_profit(data: SimData, month: str, segs: dict, prices: dict) -> dict:
    """Project a custom price for each of the four segments (the live meeting tool)."""
    out = {}
    for city in CITIES:
        total = data.net("total", city, "Pre-Tax Profit")[month]
        detail = {}
        for dp in DAYPARTS:
            util, rentals, delta = segs[(city, dp)].respond(prices[(city, dp)])
            detail[dp] = dict(utilization=util, rentals=rentals, delta=delta)
            total += delta
        out[city] = dict(profit=total, detail=detail,
                         actual=data.net("total", city, "Pre-Tax Profit")[month])
    return out


# --------------------------------------------------------------------------- #
# §4  break-even utilization
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
# §5 / §6  unit economics & weekday vs weekend contribution
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
