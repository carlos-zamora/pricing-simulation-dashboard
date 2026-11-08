"""Parser robustness on the real clipboard format (CRLF, tabs, $ % commas, no final newline)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pricing.parsers import ParseError, parse_number, parse_text
from pricing.store import Store, merge_facts

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data"


@pytest.mark.parametrize("raw,expected", [
    ("$45.00", 45.0), ("-$0.23", -0.23), ("1,000,282", 1000282.0), ("88.3%", 0.883),
    ("-0.5%", -0.005), ("32700.000000000004", 32700.0), ("", None), ("($1,200)", -1200.0),
])
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


def test_parse_number_rejects_text():
    with pytest.raises(ParseError):
        parse_number("abc")


@pytest.mark.parametrize("name,kind,count", [
    ("price_history.txt", "price", 32),
    ("unit_sales.txt", "unit_sales", 48),
    ("market_demand.txt", "market_demand", 36),
    ("fleet_size.txt", "fleet_size", 36),
    ("capacity_utilization.txt", "capacity_utilization", 36),
    ("market_research.txt", "market_research", 48),
])
def test_detect_and_count(name, kind, count):
    p = parse_text((SAMPLES / name).read_text())
    assert p.kind == kind and len(p.facts) == count and p.months == ["Jul", "Aug", "Sep", "Oct"]


@pytest.mark.parametrize("basis", ["total", "pvpm", "prv", "percentage"])
def test_net_income_basis_autodetected(basis):
    p = parse_text((SAMPLES / f"net_income_{basis}-miami.txt").read_text(), city="Miami")
    assert p.table == f"net_income_{'pct' if basis == 'percentage' else basis}"
    assert len(p.facts) == 48 and not p.warnings


def test_net_income_needs_city():
    with pytest.raises(ParseError, match="city"):
        parse_text((SAMPLES / "net_income_total-miami.txt").read_text())


def test_values_spot_check():
    p = parse_text((SAMPLES / "capacity_utilization.txt").read_text())
    f = p.facts.set_index(["city", "daypart", "field", "month"])["value"]
    assert f[("Orlando", "Weekday", "utilization", "Jul")] == 0.81
    assert f[("Florida", "Total", "orders", "Oct")] == 1000282
    t = parse_text((SAMPLES / "net_income_total-miami.txt").read_text(), city="Miami")
    g = t.facts.set_index(["field", "month"])["value"]
    assert g[("Pre-Tax Profit", "Aug")] == -75530


def test_unrecognised_text():
    with pytest.raises(ParseError):
        parse_text("hello\tworld\nfoo\tbar")
    with pytest.raises(ParseError):
        parse_text("   ")


def test_new_month_appends_and_flags_history_changes(tmp_path):
    store = Store(tmp_path / "f.csv")
    store.add_folder(SAMPLES)
    text = (SAMPLES / "price_history.txt").read_text()
    # A November row appended to the paste, and one history value edited.
    text2 = text + "\r\nNov\t$44.00\t$43.00\t$35.00\t$34.00\t$46.00\t$43.00\t$36.00\t$33.00"
    text2 = text2.replace("Aug\t$45.00", "Aug\t$47.00", 1)
    rep = store.add_text(text2, label="price")
    assert rep.months_added == ["Nov"]
    assert len(rep.changed) == 1 and "Aug" in rep.changed[0]
    assert store.months()[-1] == "Nov"
    assert store.complete_months() == ["Jul", "Aug", "Sep", "Oct"]   # Nov lacks other tables
    store.save()
    assert Store(tmp_path / "f.csv").facts.shape == store.facts.shape


def test_merge_is_idempotent():
    a = parse_text((SAMPLES / "price_history.txt").read_text()).facts
    merged, changed = merge_facts(a, a)
    assert changed == [] and len(merged) == len(a)
