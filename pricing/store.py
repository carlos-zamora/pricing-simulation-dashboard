"""Persistent, append-friendly storage of tidy facts (one CSV)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import ALL_TABLES, MONTH_ORDER, REQUIRED_TABLES, CITIES
from .parsers import FACT_COLUMNS, Parsed, ParseError, guess_city_from_name, parse_text

KEY = ["table", "city", "daypart", "firm", "field", "month"]


@dataclass
class ImportReport:
    """What happened when new text was merged in."""
    imported: list[str] = field(default_factory=list)        # human-readable lines
    months_added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)          # history that differs from before
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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


class Store:
    """Facts on disk. ``Store(path).add_text(...)`` is the whole import API."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.facts = empty_facts()
        if self.path.exists():
            self.facts = pd.read_csv(self.path, keep_default_na=False,
                                     dtype={"daypart": str, "firm": str})
            self.facts["value"] = self.facts["value"].astype(float)

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

    def complete_months(self) -> list[str]:
        """Months that have every required table (net income for both cities)."""
        needed = []
        for t in REQUIRED_TABLES:
            if t.startswith("net_income"):
                needed += [f"{t}|{c}" for c in CITIES]
            else:
                needed.append(t)
        f = self.facts
        out = []
        for m in self.months():
            fm = f[f["month"] == m]
            ok = True
            for n in needed:
                t, _, c = n.partition("|")
                sub = fm[fm["table"] == t]
                if c:
                    sub = sub[sub["city"] == c]
                if sub.empty:
                    ok = False
                    break
            # Day-period demand needs the exact screen or unit sales to estimate from.
            has_demand = any(not fm[fm["table"] == t].empty
                             for t in ("demand_by_daypart", "unit_sales"))
            if ok and has_demand:
                out.append(m)
        return out
