"""Constants shared across the package."""
from __future__ import annotations

# Order in which simulation months occur. The simulation starts in July.
BASE_MONTHS = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
               "Jan", "Feb", "Mar", "Apr", "May", "Jun"]
# The simulation can run past 12 months: the second July is "Jul 2", the third "Jul 3", etc.
MONTH_ORDER = BASE_MONTHS + [f"{m} 2" for m in BASE_MONTHS] + [f"{m} 3" for m in BASE_MONTHS]


def next_month(month: str) -> str:
    """The month after `month` in simulation order (Jun is followed by Jul 2, and so on)."""
    return MONTH_ORDER[min(MONTH_ORDER.index(month) + 1, len(MONTH_ORDER) - 1)]


CITIES = ["Orlando", "Miami"]          # cities we analyse (Florida = both combined)
DAYPARTS = ["Weekday", "Weekend"]
SEGMENTS = [(c, d) for c in CITIES for d in DAYPARTS]

# Choices offered by the two selectors. "Florida" = every city, "Both" = every day period.
FLORIDA = "Florida"
BOTH = "Both"
CITY_OPTIONS = [FLORIDA, *CITIES]
DAYPART_OPTIONS = [BOTH, *DAYPARTS]


def scope(city_sel: str | None, daypart_sel: str | None):
    """Selector values -> (cities, dayparts, segments). Unknown or empty values mean everything."""
    cities = [city_sel] if city_sel in CITIES else list(CITIES)
    dayparts = [daypart_sel] if daypart_sel in DAYPARTS else list(DAYPARTS)
    return cities, dayparts, [(c, d) for c in cities for d in dayparts]

DAYPART_ALIASES = {
    "wkdy": "Weekday", "weekday": "Weekday",
    "wknd": "Weekend", "weekend": "Weekend",
    "total": "Total",
}

# Order and spelling of the net-income lines as the simulation prints them.
NET_INCOME_LINES = [
    "Revenue from Weekday Rentals",
    "Revenue from Weekend Rentals",
    "Total Revenue",
    "Variable Costs",
    "Weighted Average Gross Profit Contribution",
    "Weekday Contribution",
    "Weekend Contribution",
    "Vehicle Inventory Costs",
    "Operating Profit Contribution",
    "Other Fixed Costs",
    "Pre-Tax Profit",
    "Accumulated Pre-Tax Profit",
]

# Net-income "bases" -> table names in the store.
#   total = whole month ($), pvpm = per vehicle per month ($),
#   prv = per rented vehicle ($), pct = percent of revenue (stored as fraction)
NET_INCOME_BASES = ["total", "pvpm", "prv", "pct"]

# Tables the dashboard needs to analyse a month, and which are optional.
REQUIRED_TABLES = {
    "price": "Price history",
    "capacity_utilization": "Capacity utilization",
    "market_demand": "Market demand",
    "unit_sales": "Unit sales",
    "fleet_size": "Fleet size",
    "market_research": "Market research",      # Univ's share among business / leisure customers
    "net_income_total": "Net income - total",
}
# Optional: never needed, because the dashboard derives them from the required tables. (Fleet size
# is required: the team sets capacity every month, so it can change.)
OPTIONAL_TABLES = {
    "net_income_prv": "Net income - per rented vehicle",
    "net_income_pvpm": "Net income - per vehicle per month",
    "net_income_pct": "Net income - % of revenue",
}
ALL_TABLES = {**REQUIRED_TABLES, **OPTIONAL_TABLES}


# What to copy each round, in the left-to-right order of the simulation's tabs (price history, market
# demand, unit sales, fleet size, capacity utilization, market research, net income): (table, city, simulation tab, selection).
# Net income screens are one item per city. Anything else the simulation can show is not needed.
COPY_LIST = [
    ("price", None, "Price history", "nothing to select"),
    ("market_demand", None, "Market demand", "nothing to select"),
    ("unit_sales", None, "Unit sales", "nothing to select"),
    ("fleet_size", None, "Fleet size", "nothing to select"),
    ("capacity_utilization", None, "Capacity utilization", "nothing to select"),
    ("market_research", None, "Market research", "nothing to select"),
    *[("net_income_total", c, "Net income", f"**City:** {c}<br>**Format:** Total") for c in CITIES],
]
assert {t for t, *_ in COPY_LIST} == set(REQUIRED_TABLES)


def item_name(table: str, city: str | None) -> str:
    """Short label for one thing to copy, e.g. 'Net income (Miami, total)'."""
    base = REQUIRED_TABLES[table].split(" - ")[0]
    return f"{base} ({city}, total)" if city else base
