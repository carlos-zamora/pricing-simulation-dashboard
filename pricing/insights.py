"""Plain-language readouts generated from the numbers, recomputed on every refresh.

Functions that describe several findings return a list of short strings (one finding each)
so the UI can show them on separate lines.
"""
from __future__ import annotations

from .charts import money
from .data import SimData
from .model import Bridge, BreakEven, DemandVsUtil, PriceGuide, PriceVsUtil


def demand_readouts(data: SimData, dvu: dict[tuple, DemandVsUtil]) -> dict[tuple, list[str]]:
    """Interpretation only; the numbers themselves are shown next to each chart."""
    out = {}
    for seg, d in dvu.items():
        util = d.table["util"]
        bits = []
        if util.max() >= 0.99:
            unfilled = data.market(seg[0], "unfilled")
            msg = f"Capacity-bound: utilization reaches {util.max():.0%}"
            if unfilled.max() > 0:
                msg += f" with up to {unfilled.max():,.0f} unfilled orders"
            bits.append(msg + ". Extra demand cannot lift utilization further.")
        if d.r2_demand is not None:
            if d.r2_demand >= 0.9:
                bits.append("Demand explains nearly all of the utilization swings.")
            elif d.r2_demand < 0.7:
                bits.append("Demand explains only part of the utilization swings, so price or "
                            "other factors matter here.")
        if d.price_slope_pts is None:
            bits.append("The Univ–Comp price gap never changed, so a price effect can't be tested.")
        elif abs(d.price_slope_pts) < 0.5:
            bits.append("After removing demand, the price effect is small.")
        else:
            bits.append("After removing demand, price still has a clear effect on utilization.")
        out[seg] = bits
    return out


def price_readouts(pvu: dict[tuple, PriceVsUtil]) -> dict[tuple, list[str]]:
    out = {}
    for seg, p in pvu.items():
        if p.slope_pts is None:
            out[seg] = ["The Univ–Comp price gap never changed, so the slope can't be measured."]
        else:
            out[seg] = ["This overstates price's effect if demand moved at the same time."]
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


def pick_readout(g: PriceGuide, data: SimData, month: str) -> list[str]:
    """The suggestion for a city as separate lines: headline first, then caveats."""
    out = []
    if not any(g.measurable.values()):
        out.append(f"**{g.city}: no price recommendation.** The data can't measure how price "
                   "affects utilization in either day period yet.")
    elif g.is_hold:
        out.append(f"**{g.city}: hold current prices.** No price change in the tested range "
                   "beats them in the worse of the two cases.")
    else:
        out.append(f"**{g.city}: ${g.pick_weekday:.0f} weekday / ${g.pick_weekend:.0f} weekend.** "
                   f"Profit {money(g.cautious_delta, True)} (cautious) to "
                   f"{money(g.optimistic_delta, True)} (optimistic) vs {month}.")
        if g.on_edge:
            out.append("The pick sits at the edge of the tested range: go in steps and re-check.")
    for dp in g.held:
        line = (f"{g.city} {dp.lower()} price held: the data can't measure how price affects "
                "utilization there")
        util = data.utilization(g.city, dp)[month]
        unfilled = data.market(g.city, "unfilled")[month]
        if util >= 0.99 and unfilled > 0:
            demand = data.demand(g.city, dp)[month]
            line += (f" (at capacity with {unfilled:,.0f} unfilled orders, {unfilled / demand:.0%} "
                     "of demand, so a price rise is plausible, but how far is unknown; test in "
                     "small steps)")
        out.append(line + ".")
    return out


def caveats(data: SimData) -> list[str]:
    out = []
    n = len(data.months)
    if n < 6:
        out.append(f"Only {n} months of data: treat slopes as directional.")
    return out
