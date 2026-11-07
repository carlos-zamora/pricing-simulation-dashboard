"""Constants shared across the package."""
from __future__ import annotations

# Order in which simulation months occur. The simulation starts in July.
MONTH_ORDER = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
               "Jan", "Feb", "Mar", "Apr", "May", "Jun"]

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
    "net_income_total": "Net income - total",
    "net_income_prv": "Net income - per rented vehicle",
}
OPTIONAL_TABLES = {
    "fleet_size": "Fleet size",
    "net_income_pvpm": "Net income - per vehicle per month",
    "net_income_pct": "Net income - % of revenue",
}
ALL_TABLES = {**REQUIRED_TABLES, **OPTIONAL_TABLES}
