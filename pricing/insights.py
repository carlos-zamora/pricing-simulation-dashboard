"""Plain-language readouts generated from the numbers (the workbook's 'Insight' cells were
typed by hand and went stale; these are recomputed every time)."""
from __future__ import annotations

from .charts import money
from .config import CITIES, SEGMENTS
from .data import SimData
from .model import (Bridge, BreakEven, DemandVsUtil, PriceVsUtil, WhatIfGrid)


def demand_readouts(data: SimData, dvu: dict[tuple, DemandVsUtil]) -> dict[tuple, str]:
    out = {}
    for seg, d in dvu.items():
        util = d.table["util"]
        bits = []
        if util.max() >= 0.99:
            unfilled = data.market(seg[0], "unfilled")
            bits.append(f"Capacity-bound: utilization hits {util.max():.0%}"
                        + (f" with {unfilled.max():,.0f} unfilled orders in the worst month"
                           if unfilled.max() > 0 else "")
                        + ", so demand can't lift it further and price is not the constraint.")
        elif d.r2_demand is not None and d.r2_demand >= 0.9:
            bits.append(f"Demand explains {d.r2_demand:.0%} of utilization swings "
                        f"(~{d.demand_slope_pts_per_10k:+.1f} pts per 10K orders).")
        elif d.r2_demand is not None:
            bits.append(f"Demand explains only {d.r2_demand:.0%} of utilization swings.")
        if d.price_slope_pts is None:
            bits.append("The Univ–Comp gap never changed, so the price effect can't be tested.")
        else:
            bits.append(f"After removing demand, each +$1 of price gap moves utilization "
                        f"{d.price_slope_pts:+.1f} pts.")
        out[seg] = " ".join(bits)
    return out


def price_readouts(pvu: dict[tuple, PriceVsUtil]) -> dict[tuple, str]:
    out = {}
    for seg, p in pvu.items():
        if p.slope_pts is None:
            out[seg] = "Gap never changed, so the gap-only slope can't be measured."
        else:
            out[seg] = (f"Gap alone: {p.slope_pts:+.1f} util pts per +$1 (R² {p.r2:.2f}). "
                        "This overstates price's effect if demand moved at the same time.")
    return out


def bridge_readout(b: Bridge) -> str:
    drivers = b.steps[1:-1]
    top = max(drivers, key=lambda s: abs(s[1]))
    price = dict(drivers)["Price effect"]
    vol = dict(drivers)["Volume effect"]
    return (f"{b.city}: price {money(price, True)} and volume {money(vol, True)} "
            f"→ profit {money(b.end - b.start, True)} from {b.base} to {b.compare}. "
            f"Largest driver: {top[0].lower()}.")


def break_even_readout(be: BreakEven) -> str:
    key = f"@ {be.month} prices"
    cushion = (be.actual_util - be.break_even[key]) * 100
    word = "cushion" if cushion >= 0 else "shortfall"
    return (f"{be.city}: break-even {be.break_even[key]:.0%} vs {be.actual_util:.0%} actual "
            f"({abs(cushion):.1f} pt {word}).")


def weekend_readout(data: SimData, city: str, month: str) -> str | None:
    u = data.utilization(city, "Weekend")[month]
    if u < 0.5:
        return (f"{city} weekend fleet is mostly idle ({u:.0%} utilization): consider "
                "redeploying cars or a weekend promotion test.")
    return None


def whatif_readout(g: WhatIfGrid) -> str:
    if abs(g.best_vs_actual) < 1:
        return f"{g.city}: current prices are the best in the grid."
    return (f"{g.city}: best grid prices are ${g.best_weekday:.0f} weekday / "
            f"${g.best_weekend:.0f} weekend ({money(g.best_vs_actual, True)} vs actual).")


def caveats(data: SimData) -> list[str]:
    out = []
    n = len(data.months)
    if n < 6:
        out.append(f"Only {n} months of data: treat slopes as directional.")
    if data.demand_estimated:
        out.append("Demand by day period was estimated from unit sales + unfilled orders "
                   "(paste the 'demand by day period' screen for exact values).")
    return out
