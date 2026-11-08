"""Market research: business vs leisure price sensitivity."""
from __future__ import annotations

from pathlib import Path

import pytest

from pricing import insights, model
from pricing.data import SimData
from pricing.parsers import parse_text
from pricing.store import Store

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data"


def _store(tmp_path, research: bool = True) -> Store:
    s = Store(tmp_path / "_test_facts.csv")
    for f in sorted(SAMPLES.glob("*.txt")):
        if research or f.stem != "market_research":
            s.add_text(f.read_text(encoding="utf-8-sig"), city=_city(f.stem), label=f.name)
    return s


def _city(stem: str) -> str | None:
    return "Miami" if "miami" in stem else "Orlando" if "orlando" in stem else None


@pytest.fixture
def fits(tmp_path):
    s = _store(tmp_path)
    return model.research_sensitivity(SimData(s.facts, s.complete_months()))


def test_research_values_parsed_as_fractions():
    p = parse_text((SAMPLES / "market_research.txt").read_text())
    f = p.facts
    row = f[(f.city == "Orlando") & (f.daypart == "Weekday") & (f.field == "share_leisure")
            & (f.month == "Oct")]
    assert row["value"].item() == pytest.approx(0.51)
    assert set(f["firm"]) == {"Univ"}


def test_research_is_required(tmp_path):
    s = _store(tmp_path, research=False)
    assert s.complete_months() == []
    assert s.missing("Oct") == ["Market research"]
    assert _store(tmp_path).complete_months() == ["Jul", "Aug", "Sep", "Oct"]


def test_orlando_weekday_leisure_more_sensitive(fits):
    f = fits[("Orlando", "Weekday")]
    assert f.status == model.RESEARCH_OK
    assert f.slope["leisure"] == pytest.approx(-1.0, abs=0.05)
    assert f.slope["business"] == pytest.approx(-0.2, abs=0.05)
    assert abs(f.elasticity["leisure"]) > abs(f.elasticity["business"])
    assert f.ratio == pytest.approx(5.0, abs=0.3)
    ins = insights.research_insight(f)
    assert "leisure customers react more" in ins[0]
    assert insights.research_oneliner(f) is not None


def test_orlando_weekend_business_flat(fits):
    f = fits[("Orlando", "Weekend")]
    assert f.status == model.RESEARCH_OK
    assert f.slope["business"] == pytest.approx(0.0, abs=1e-9)
    assert f.ratio is None                                  # no "N×" claim when business is flat
    assert "business didn't move" in insights.research_insight(f)[0]


@pytest.mark.parametrize("seg,status", [(("Miami", "Weekday"), model.RESEARCH_CAPPED),
                                        (("Miami", "Weekend"), model.RESEARCH_NO_GAP)])
def test_miami_not_measurable_and_no_claim(fits, seg, status):
    f = fits[seg]
    assert f.status == status and not f.measurable
    text = " ".join(insights.research_insight(f))
    assert "can't be measured" in text and "react more" not in text
    assert insights.research_oneliner(f) is None
