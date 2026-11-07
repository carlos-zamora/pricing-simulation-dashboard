"""Headless run of the Streamlit app on the sample data."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _own_data_file(tmp_path, monkeypatch):
    """Never depend on (or write) the real data/facts.csv: start from the bundled sample."""
    monkeypatch.setenv("PRICING_SIM_DATA", str(tmp_path / "facts.csv"))


def _run(city=None, daypart=None) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    if city or daypart:
        if city:
            at.sidebar.radio(key="city_sel").set_value(city)
        if daypart:
            at.sidebar.radio(key="daypart_sel").set_value(daypart)
        at.run()
    return at


def _text(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)


def test_default_view_is_florida_both_and_compares_latest_to_previous_month():
    data_file = ROOT / "data" / "facts.csv"
    existed = data_file.exists()
    try:
        at = _run()
        assert not at.exception
        assert [r.key for r in at.sidebar.radio] == ["city_sel", "daypart_sel"]
        assert not at.sidebar.selectbox and not at.selectbox   # city picker appears only on paste
        text = _text(at)
        assert "Analysing **Oct** against **Sep**" in text
        assert "Showing: **Orlando + Miami** · **Weekday + Weekend**" in text
        assert "Our prices and capacity for Nov" in text
        assert "no game month played yet" in text.lower()      # sample data: profit shows $0
        assert "no price recommendation" in text.lower()                # Miami explained, not hidden
        md = [m.value for m in at.markdown]
        assert md.index("**Orlando**") < md.index("**Miami**")  # readouts grouped by city
    finally:
        if not existed and data_file.exists():
            data_file.unlink()


@pytest.mark.parametrize("city", ["Florida", "Orlando", "Miami"])
@pytest.mark.parametrize("daypart", ["Both", "Weekday", "Weekend"])
def test_every_selector_combination_runs(city, daypart):
    data_file = ROOT / "data" / "facts.csv"
    existed = data_file.exists()
    try:
        at = _run(city, daypart)
        assert not at.exception
        assert len(at.number_input) == 6          # 4 price controls (every segment) + 2 fleet sizes (per city)
        if city == "Miami":
            assert "Orlando:" not in _text(at)
    finally:
        if not existed and data_file.exists():
            data_file.unlink()


def test_reset_button_puts_back_last_months_prices_and_fleets():
    at = _run()
    assert not at.exception
    assert not [b for b in at.button if "Fill with suggested" in b.label]   # auto-populated instead
    start = [n.value for n in at.number_input]
    assert len(start) == 6
    for n in at.number_input:
        n.set_value(n.value + 5)
    at.run()
    assert [n.value for n in at.number_input] != start
    reset = at.button(key="reset_plan")
    assert reset.label == "Reset to Oct prices"
    reset.click().run()
    assert not at.exception
    assert [n.value for n in at.number_input] == start   # sample data: suggestion = hold = Oct prices
