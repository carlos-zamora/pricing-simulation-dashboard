"""Persistent, append-friendly storage of tidy facts (one CSV)."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import ALL_TABLES, CITIES, COPY_LIST, MONTH_ORDER, item_name
from .parsers import (FACT_COLUMNS, Parsed, ParseError, guess_city_from_name, parse_text,
                      split_tables)

KEY = ["table", "city", "daypart", "firm", "field", "month"]


@dataclass
class ImportReport:
    """What happened when new text was merged in."""
    imported: list[str] = field(default_factory=list)        # human-readable lines
    months_added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)          # history that differs from before
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)       # net income texts still needing a city


@lru_cache(maxsize=4)
def _sample_facts(sample_dir: str) -> pd.DataFrame:
    store = Store(Path(sample_dir) / "__never_saved__.csv")
    store.add_folder(sample_dir)
    return store.facts


def sample_months(facts: pd.DataFrame, sample_dir: str | Path) -> list[str]:
    """Months in `facts` that are just the bundled sample (every value identical to it).

    A real game month never matches, so these are months that were not actually played."""
    sample_dir = Path(sample_dir)
    if facts.empty or not sample_dir.exists():
        return []
    sample_facts = _sample_facts(str(sample_dir))
    cols = [*KEY]

    def rows(df: pd.DataFrame, month: str) -> set:
        part = df[df["month"] == month]
        return set(zip(*(part[c] for c in cols), part["value"].round(6)))

    return [m for m in facts["month"].unique()
            if rows(sample_facts, m) and rows(facts, m) <= rows(sample_facts, m)]


def empty_facts() -> pd.DataFrame:
    return pd.DataFrame(columns=FACT_COLUMNS)


def merge_facts(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Merge ``new`` into ``old``; new values win. Also report changed history."""
    if old.empty:
        return new.copy(), []
    o = old.set_index(KEY)["value"]
    n = new.set_index(KEY)["value"]
    both = o.index.intersection(n.index)
    diff = (o.loc[both] - n.loc[both]).abs() > 1e-6
    changed = []
    for key in both[diff.values]:
        t, c, d, f, fld, m = key
        changed.append(f"{t} / {c} {d} {f} {fld} / {m}: {o.loc[key]:g} -> {n.loc[key]:g}")
    merged = n.combine_first(o).reset_index()
    return merged[FACT_COLUMNS], changed


def sort_facts(df: pd.DataFrame) -> pd.DataFrame:
    order = {m: i for i, m in enumerate(MONTH_ORDER)}
    return (df.assign(_o=df["month"].map(order))
              .sort_values(["table", "city", "daypart", "firm", "field", "_o"])
              .drop(columns="_o").reset_index(drop=True))


# A net income table is matched to the city whose prices (and unit sales) it reproduces.
# Unit sales are rounded to thousands, so a true match is off by a percent or so, while
# Orlando and Miami differ by tens of percent.
_CITY_MATCH_MAX, _CITY_OTHER_MIN = 0.05, 0.10


def infer_net_income_city(parsed: Parsed, facts: pd.DataFrame) -> str | None:
    """Which city a net income table belongs to, judged from the numbers (None = can't tell).

    Only the total basis can be placed: weekday and weekend revenue must equal our price x our
    unit sales in that city. The per-vehicle and % screens carry nothing that separates the
    cities (both cities often charge the same price), so they need the city given.
    """
    if parsed.kind != "net_income" or parsed.table != "net_income_total":
        return None
    ours = facts[facts["firm"] == "Univ"]
    scores: dict[str, float] = {}
    for city in CITIES:
        errs = []
        for dp in ("Weekday", "Weekend"):
            line = parsed.facts[parsed.facts["field"] == f"Revenue from {dp} Rentals"]
            price = ours[(ours["table"] == "price") & (ours["city"] == city)
                         & (ours["daypart"] == dp)].set_index("month")["value"]
            units = ours[(ours["table"] == "unit_sales") & (ours["city"] == city)
                         & (ours["daypart"] == dp)].set_index("month")["value"]
            for month, rev in line.set_index("month")["value"].items():
                if month not in price.index:
                    continue
                if month in units.index:
                    errs.append(abs(rev / (price[month] * units[month]) - 1))
        if errs:
            scores[city] = sum(errs) / len(errs)
    if len(scores) < len(CITIES):
        return None
    best = min(scores, key=scores.get)
    others = [v for c, v in scores.items() if c != best]
    if scores[best] <= _CITY_MATCH_MAX and all(v >= _CITY_OTHER_MIN for v in others):
        return best
    return None


class Store:
    """Facts on disk. ``Store(path).add_text(...)`` is the whole import API."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.facts = empty_facts()
        if self.path.exists():
            self.facts = pd.read_csv(self.path, keep_default_na=False,
                                     dtype={"daypart": str, "firm": str})
            self.facts["value"] = self.facts["value"].astype(float)
            # Drop tables this version no longer uses (e.g. an older 'demand_by_daypart').
            self.facts = self.facts[self.facts["table"].isin(ALL_TABLES)].reset_index(drop=True)

    # -- writing ----------------------------------------------------------- #
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sort_facts(self.facts).to_csv(self.path, index=False)

    def clear(self) -> None:
        self.facts = empty_facts()

    def add_parsed(self, parsed: Parsed, report: ImportReport | None = None,
                   label: str = "") -> ImportReport:
        report = report or ImportReport()
        before = set(self.facts["month"]) if not self.facts.empty else set()
        self.facts, changed = merge_facts(self.facts, parsed.facts)
        report.changed += changed
        report.warnings += parsed.warnings
        new_months = [m for m in parsed.months if m not in before]
        report.months_added += [m for m in new_months if m not in report.months_added]
        where = f"{parsed.table}" + (f" ({parsed.city})" if parsed.city else "")
        report.imported.append(f"{label or 'pasted text'} -> {where}: "
                               f"{len(parsed.facts)} values, months {', '.join(parsed.months)}")
        return report

    def add_text(self, text: str, city: str | None = None, label: str = "",
                 report: ImportReport | None = None) -> ImportReport:
        report = report or ImportReport()
        try:
            parsed = parse_text(text, city=city)
        except ParseError as exc:
            report.errors.append(f"{label or 'pasted text'}: {exc}")
            return report
        return self.add_parsed(parsed, report, label)

    def add_pasted(self, text: str, city: str | None = None, label: str = "Table",
                   report: ImportReport | None = None) -> ImportReport:
        """Import one paste holding any number of tables, in any order.

        Net income screens carry no city: it is detected from the prices and unit sales (already
        stored, or pasted in the same go). Screens it can't place are left in
        ``report.unresolved`` unless ``city`` says which city they are.
        """
        report = report or ImportReport()
        parsed: list[tuple[str, Parsed]] = []
        for i, block in enumerate(split_tables(text), 1):
            try:
                parsed.append((block, parse_text(block, city=city, defer_city=True)))
            except ParseError as exc:
                report.errors.append(f"{label} {i}: {exc}")
        # Prices and unit sales to match net income against: stored ones plus this paste's
        # (which repeat earlier months; the pasted value wins).
        reference = (pd.concat([self.facts] + [p.facts for _, p in parsed
                                               if p.kind != "net_income"], ignore_index=True)
                       .drop_duplicates(KEY, keep="last"))
        for i, (block, p) in enumerate(parsed, 1):
            note = ""
            if p.kind == "net_income" and p.city is None:
                found = infer_net_income_city(p, reference)
                if found is None:
                    report.unresolved.append(block)
                    continue
                p, note = p.with_city(found), " (city detected from prices and sales)"
            self.add_parsed(p, report, label=f"{label} {i}{note}")
        return report

    def add_folder(self, folder: str | Path) -> ImportReport:
        """Import every .txt file in a folder (city for net income taken from file name)."""
        report = ImportReport()
        files = sorted(Path(folder).glob("*.txt"))
        if not files:
            report.errors.append(f"No .txt files found in {folder}")
        for f in files:
            text = f.read_text(encoding="utf-8-sig")
            self.add_text(text, city=guess_city_from_name(f.stem), label=f.name, report=report)
        return report

    # -- reading ----------------------------------------------------------- #
    def months(self) -> list[str]:
        have = set(self.facts["month"])
        return [m for m in MONTH_ORDER if m in have]

    def coverage(self) -> pd.DataFrame:
        """Months x tables: how many values we hold (0 = missing). Net income is per city."""
        if self.facts.empty:
            return pd.DataFrame()
        f = self.facts.copy()
        f["tbl"] = f["table"]
        ni = f["table"].str.startswith("net_income")
        f.loc[ni, "tbl"] = f.loc[ni, "table"] + " [" + f.loc[ni, "city"].str[:3] + "]"
        cov = f.pivot_table(index="month", columns="tbl", values="value",
                            aggfunc="count", fill_value=0)
        cov = cov.reindex([m for m in MONTH_ORDER if m in cov.index])
        return cov

    def missing(self, month: str) -> list[str]:
        """What is still needed before ``month`` can be analysed (empty = complete)."""
        f = self.facts[self.facts["month"] == month]
        out = []
        for table, city, _, _ in COPY_LIST:
            sub = f[f["table"] == table]
            if city:
                sub = sub[sub["city"] == city]
            if sub.empty:
                out.append(item_name(table, city))
        return out

    def complete_months(self) -> list[str]:
        """Months that have every required table (net income for both cities)."""
        return [m for m in self.months() if not self.missing(m)]

    def newest_month(self) -> str | None:
        """The latest month any table mentions (it may still be incomplete)."""
        months = self.months()
        return months[-1] if months else None
