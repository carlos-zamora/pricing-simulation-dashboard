"""Plain-language readouts generated from the numbers, recomputed on every refresh.

Functions that describe several findings return a list of short strings (one finding each)
so the UI can show them on separate lines.
"""
from __future__ import annotations

from .charts import money
from .data import SimData
from .model import Bridge, BreakEven, DemandVsUtil, PriceGuide, PriceVsUtil

GOOD, BAD, INFO = "good", "bad", "info"      # green / red / yellow font color in the UI


class Insight(list):
    """[headline, *support lines] plus a tone: GOOD (positive news), BAD (negative), INFO (other).

    A plain list of strings to any code that ignores the tone."""

    def __init__(self, lines, tone: str = INFO):
        super().__init__(lines)
        self.tone = tone


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


def profit_insight(b: Bridge) -> Insight:
    """Headline: did profit rise or fall and why. Support: the four effects."""
    steps = dict(b.steps[1:-1])
    drivers = {k: v for k, v in steps.items() if k != "Rounding in source"}
    top = max(drivers, key=lambda k: abs(drivers[k]))
    change = b.end - b.start
    verb = "rose" if change > 0 else "fell" if change < 0 else "was flat"
    head = (f"**Profit {verb} {money(abs(change))}** vs {b.base} "
            f"(now {money(b.end)}), mainly from {top.lower()}.")
    support = (f"Price {money(steps['Price effect'], True)} · volume {money(steps['Volume effect'], True)}"
               f" · variable cost {money(steps['Variable cost / rental'], True)}"
               f" · fixed costs {money(steps['Fixed costs'], True)}")
    return Insight([head, support], GOOD if change > 0 else BAD if change < 0 else INFO)


def _colored(text: str, v: float | None) -> str:
    """Streamlit color directive: green for good, red for bad, yellow for important/neutral."""
    if v is None or abs(v) < 0.5:
        return f":yellow[{text}]"
    return f":{'green' if v > 0 else 'red'}[{text}]"


def profit_oneliner(name: str, b: Bridge) -> str:
    """What moved profit, in one line. Colors: headline green/red by direction, each effect
    green/red by sign, and the biggest driver in yellow (the important part)."""
    steps = dict(b.steps[1:-1])
    drivers = {k: v for k, v in steps.items() if k != "Rounding in source"}
    top = max(drivers, key=lambda k: abs(drivers[k]))
    change = b.end - b.start
    verb = "rose" if change > 0 else "fell" if change < 0 else "was flat"
    parts = [f"{label.lower()} {_colored(money(steps[key], True), steps[key])}"
             for label, key in (("Price", "Price effect"), ("volume", "Volume effect"),
                                ("variable cost", "Variable cost / rental"),
                                ("fixed costs", "Fixed costs"))]
    return (f"**{name}:** " + _colored(f"**profit {verb} {money(abs(change))}**", change)
            + f" vs {b.base} (now {money(b.end)}), mainly from :yellow[{top.lower()}] ("
            + " · ".join(parts) + ")")


def break_even_insight(be: BreakEven) -> Insight:
    key = f"@ {be.month} prices"
    cushion = (be.actual_util - be.break_even[key]) * 100
    word = "cushion above" if cushion >= 0 else "shortfall below"
    return Insight([f"**{abs(cushion):.1f} pt {word} break-even.**",
                    f"Break-even {be.break_even[key]:.0%} vs {be.actual_util:.0%} actual utilization."],
                   GOOD if cushion >= 0 else BAD)


def idle_weekend_insight(data: SimData, city: str, month: str) -> Insight:
    u = data.utilization(city, "Weekend")[month]
    if u < 0.5:
        return Insight([f"**Weekend fleet is mostly idle** ({u:.0%} utilization).",
                        "Consider redeploying cars or a weekend promotion test."], INFO)
    return Insight([], INFO)


def price_insight(g: PriceGuide, data: SimData, month: str) -> Insight:
    """pick_readout without the city name: the city heading above already says it."""
    lines = pick_readout(g, data, month)
    head = lines[0].replace(f"{g.city}: ", "", 1)
    out = [head[:2] + head[2:3].upper() + head[3:]]          # "**hold" -> "**Hold"
    for line in lines[1:]:
        line = line.replace(f"{g.city} ", "", 1)
        out.append(line[:1].upper() + line[1:])
    # Green only when a price change is recommended (better profit even in the worse case);
    # holding or having no recommendation is neutral news.
    recommended = any(g.measurable.values()) and not g.is_hold
    return Insight(out, GOOD if recommended else INFO)


def city_readouts(city: str, guide: PriceGuide, bridge: Bridge, be: BreakEven, data: SimData,
                  month: str, dayparts: list[str]) -> list[Insight]:
    """Insights for one city, most decision-relevant first. Each is [headline, *support]."""
    out = [price_insight(guide, data, month), profit_insight(bridge), break_even_insight(be)]
    if "Weekend" in dayparts:
        idle = idle_weekend_insight(data, city, month)
        if idle:
            out.append(idle)
    return out


def slope_insight(segs_cautious: dict, segs_optimistic: dict,
                  segments: list[tuple[str, str]]) -> list[Insight]:
    """One insight per segment: the price-sensitivity range used by the planner."""
    out = []
    for seg in segments:
        c, o = segs_cautious[seg], segs_optimistic[seg]
        if c.slope_used >= 0:
            out.append(Insight([f"**{c.name}: not measurable yet, price held.**",
                                "The data can't show how price moves utilization here."]))
        else:
            lo, hi = sorted((abs(c.slope_used), abs(o.slope_used)))
            out.append(Insight([f"**{c.name}:** utilization falls {lo:.1f} to {hi:.1f} pts per +$1 of price.",
                                f"Cautious {c.slope_used:+.1f} (all movement credited to price) · "
                                f"optimistic {o.slope_used:+.1f} (after removing demand)."]))
    return out


def price_segment_insight(p: PriceVsUtil, readout: list[str]) -> Insight:
    if p.slope_pts is None:
        return Insight([f"**{readout[0]}**", "Gap slope: n/a · R²: n/a"])
    if p.slope_pts < 0:
        head = "Months with a bigger price gap had lower utilization."
    else:
        head = "Utilization did not fall when the price gap grew."
    r2 = "n/a" if p.r2 is None else f"{p.r2:.2f}"
    return Insight([f"**{head}**", f"Gap slope {p.slope_pts:+.1f} util pts per +$1 gap · R² {r2}",
                    *readout])


def demand_segment_insight(d: DemandVsUtil, readout: list[str]) -> Insight:
    r2 = "n/a" if d.r2_demand is None else f"{d.r2_demand:.2f}"
    ds = "n/a" if d.demand_slope_pts_per_10k is None else f"{d.demand_slope_pts_per_10k:+.1f}"
    ps = "n/a" if d.price_slope_pts is None else f"{d.price_slope_pts:+.1f}"
    return Insight([f"**{readout[0]}**",
                    f"R² vs demand {r2} · demand slope {ds} util pts per 10K orders",
                    f"Price slope after demand {ps} util pts per +$1 gap",
                    *readout[1:]])


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
