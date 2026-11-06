"""Parse the tab-separated tables the simulation puts on the clipboard.

Every parser returns *tidy facts*: one row per number with the columns
``table, city, daypart, firm, field, month, value``. Storing everything in that
one shape is what lets a new month be appended without touching any formulas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import DAYPART_ALIASES, MONTH_ORDER, NET_INCOME_LINES

FACT_COLUMNS = ["table", "city", "daypart", "firm", "field", "month", "value"]


class ParseError(ValueError):
    """Raised when pasted text is not a recognised simulation table."""


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #
def parse_number(raw: str) -> float | None:
    """'$1,234.50' -> 1234.5, '-$0.23' -> -0.23, '88.3%' -> 0.883, '' -> None."""
    s = raw.strip()
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    pct = s.endswith("%")
    s = s.rstrip("%").replace("$", "").replace(",", "").strip()
    try:
        value = float(s)
    except ValueError as exc:
        raise ParseError(f"Cannot read {raw!r} as a number") from exc
    if negative:
        value = -value
    if pct:
        value /= 100.0
    # The simulation prints values like 32700.000000000004; clean that up.
    return round(value, 9)


def normalize_month(raw: str) -> str:
    m = raw.strip()[:3].title()
    if m not in MONTH_ORDER:
        raise ParseError(f"{raw!r} is not a month name")
    return m


def read_grid(text: str) -> list[list[str]]:
    """Split pasted text into a rectangular grid of cells (handles CRLF, no final newline)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        raise ParseError("Nothing to parse: the text is empty")
    grid = [line.split("\t") for line in lines]
    if not any(len(row) > 1 for row in grid):
        raise ParseError("No tab-separated columns found. Copy the table straight from "
                         "the simulation (do not retype it).")
    width = max(len(r) for r in grid)
    return [r + [""] * (width - len(r)) for r in grid]


def _ffill(row: list[str]) -> list[str]:
    """Forward-fill merged header cells ('Orlando', '', '', 'Miami', ...)."""
    out, cur = [""], ""
    for cell in row[1:]:
        cell = cell.strip()
        if cell:
            cur = cell
        out.append(cur)
    return out


# --------------------------------------------------------------------------- #
# Table kinds
# --------------------------------------------------------------------------- #
def _fleet_field(label: str) -> tuple[str, str]:
    return {
        "Fleet Size": ("fleet_size", ""),
        "Daily Wkdy Orders": ("daily_orders", "Weekday"),
        "Daily Wknd Orders": ("daily_orders", "Weekend"),
    }[label]


_MARKET_FIELDS = {"Market Demand": "demand", "Total Sales": "sales", "Unfilled Orders": "unfilled"}


def _levels_to_fact(kind: str, levels: list[str]) -> tuple[str, str, str, str]:
    """(city, daypart, firm, field) from the stacked header labels of one column."""
    if kind in ("price", "unit_sales"):
        city, daypart, firm = levels
        return city, daypart, firm, "price" if kind == "price" else "units"
    if kind in ("capacity_utilization", "demand_by_daypart"):
        city, group, sub = levels
        daypart = DAYPART_ALIASES.get(sub.lower())
        if daypart is None:
            raise ParseError(f"Unexpected column label {sub!r}")
        return city, daypart, "", group.lower()
    if kind == "fleet_size":
        city, label = levels
        fld, daypart = _fleet_field(label)
        return city, daypart, "", fld
    if kind == "market_demand":
        city, label = levels
        return city, "", "", _MARKET_FIELDS[label]
    raise ParseError(f"Unknown table kind {kind}")


def detect_kind(grid: list[list[str]]) -> str:
    """Work out which simulation screen a grid came from."""
    first = grid[0]
    # Net income tables are transposed: 'Month  July  August ...' is the first row.
    if first[0].strip().lower() == "month":
        try:
            normalize_month(first[1])
        except ParseError:
            pass
        else:
            return "net_income"
    hdr = _month_row(grid)
    fields = {c.strip() for c in grid[hdr][1:] if c.strip()}
    groups = [{c.strip() for c in row[1:] if c.strip()} for row in grid[:hdr]]
    if {"Univ", "Comp"} <= fields:
        return "unit_sales" if any("Florida" in g for g in groups) else "price"
    if "Fleet Size" in fields:
        return "fleet_size"
    if "Market Demand" in fields:
        return "market_demand"
    if fields <= {"Wkdy", "Wknd", "Total"} and len(groups) >= 2:
        if "Utilization" in groups[1]:
            return "capacity_utilization"
        if "Demand" in groups[1]:
            return "demand_by_daypart"
    raise ParseError("Could not recognise this table. Expected one of: price history, unit "
                     "sales, market demand, fleet size, capacity utilization, demand by day "
                     "period or a net income screen.")


def _month_row(grid: list[list[str]]) -> int:
    for i, row in enumerate(grid):
        if row[0].strip().lower() == "month":
            return i
    raise ParseError("Could not find the header row that starts with 'Month'")


def detect_net_income_basis(grid: list[list[str]]) -> str:
    """total / pvpm / prv / pct, judged from the numbers themselves."""
    body = [c for row in grid[1:] for c in row[1:]]
    if any("%" in c for c in body):
        return "pct"
    for row in grid[1:]:
        if row[0].strip() == "Total Revenue":
            value = abs(parse_number(row[-1]) or 0)
            if value > 100_000:
                return "total"
            return "pvpm" if value > 200 else "prv"
    raise ParseError("Net income table has no 'Total Revenue' row")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
@dataclass
class Parsed:
    kind: str                      # e.g. 'price', 'net_income'
    table: str                     # store table name, e.g. 'net_income_total'
    facts: pd.DataFrame
    city: str | None = None        # only for net income
    warnings: list[str] = field(default_factory=list)

    @property
    def months(self) -> list[str]:
        return [m for m in MONTH_ORDER if m in set(self.facts["month"])]


def parse_text(text: str, city: str | None = None, basis: str | None = None) -> Parsed:
    """Parse one pasted table. ``city`` is required for net-income screens."""
    grid = read_grid(text)
    kind = detect_kind(grid)
    if kind == "net_income":
        return _parse_net_income(grid, city, basis)

    hdr = _month_row(grid)
    stacked = [_ffill(r) for r in grid[:hdr]]
    field_row = [c.strip() for c in grid[hdr]]
    rows: list[dict] = []
    for data_row in grid[hdr + 1:]:
        if not data_row[0].strip():
            continue
        month = normalize_month(data_row[0])
        for j in range(1, len(field_row)):
            if not field_row[j]:
                continue
            value = parse_number(data_row[j])
            if value is None:
                continue
            levels = [s[j] for s in stacked] + [field_row[j]]
            c, dp, firm, fld = _levels_to_fact(kind, levels)
            rows.append(dict(table=kind, city=c, daypart=dp, firm=firm, field=fld,
                             month=month, value=value))
    if not rows:
        raise ParseError("The table has a header but no data rows")
    return Parsed(kind=kind, table=kind, facts=pd.DataFrame(rows, columns=FACT_COLUMNS))


def _parse_net_income(grid: list[list[str]], city: str | None, basis: str | None) -> Parsed:
    if not city:
        raise ParseError("Net income screens do not say which city they belong to. "
                         "Choose Orlando or Miami.")
    basis = basis or detect_net_income_basis(grid)
    months = [normalize_month(c) for c in grid[0][1:] if c.strip()]
    rows: list[dict] = []
    seen: list[str] = []
    for row in grid[1:]:
        label = row[0].strip()
        if not label:
            continue
        seen.append(label)
        for month, cell in zip(months, row[1:]):
            value = parse_number(cell)
            if value is not None:
                rows.append(dict(table=f"net_income_{basis}", city=city, daypart="", firm="",
                                 field=label, month=month, value=value))
    missing = [l for l in NET_INCOME_LINES if l not in seen]
    warnings = [f"Missing net-income lines: {', '.join(missing)}"] if missing else []
    if not rows:
        raise ParseError("The net income table has no data rows")
    return Parsed(kind="net_income", table=f"net_income_{basis}",
                  facts=pd.DataFrame(rows, columns=FACT_COLUMNS), city=city, warnings=warnings)


def guess_city_from_name(name: str) -> str | None:
    n = name.lower()
    for city in ("orlando", "miami"):
        if city in n:
            return city.title()
    return None
