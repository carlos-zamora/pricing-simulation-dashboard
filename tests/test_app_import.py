"""The import box: paste the six tabs for a new month in one go, or only some of them."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from pricing.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data"


def _november(name: str) -> str:
    """A sample screen with a November added (copy of October), as the simulation would paste it."""
    lines = (SAMPLES / name).read_bytes().decode("utf-8-sig").split("\r\n")
    if name.startswith("net_income"):                     # months run across the columns
        out = []
        for i, line in enumerate(lines):
            cells = line.split("\t")
            out.append("\t".join(cells + ["November" if i == 0 else cells[-1]]))
        return "\r\n".join(out)
    last = lines[-1].split("\t")
    return "\r\n".join(lines + ["\t".join(["Nov"] + last[1:])])


SIX = ["price_history", "unit_sales", "market_demand", "capacity_utilization",
       "net_income_total-orlando", "net_income_total-miami"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICING_SIM_DATA", str(tmp_path / "facts.csv"))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()


def _text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [w.value for w in at.warning] + [s.value for s in at.success]
    return "\n".join(parts)


def _paste(at: AppTest, names, sep="") -> AppTest:
    at.text_area(key="paste_text").set_value(sep.join(_november(f"{n}.txt") for n in names))
    return at.run()


def test_copy_list_is_shown_next_to_the_box(app):
    assert not app.exception
    text = _text(app)
    for tab in ("Price history", "Unit sales", "Market demand", "Capacity utilization"):
        assert f"**{tab}**" in text
    for city in ("Orlando", "Miami"):
        assert f"**City:** {city}<br>**Format:** Total" in text
    assert "Copy these 6 tabs" in text


@pytest.mark.parametrize("sep", ["", "\r\n"])
def test_pasting_the_six_tabs_adds_the_new_month(app, tmp_path, sep):
    at = _paste(app, SIX, sep)
    assert not at.exception and not at.warning
    assert at.text_area(key="paste_text").value == ""             # emptied after importing
    assert not at.selectbox                                       # no city question
    assert "Analysing **Nov** against **Oct**" in _text(at)
    assert Store(tmp_path / "facts.csv").complete_months()[-1] == "Nov"


def test_partial_paste_shows_a_banner_and_keeps_the_last_full_month(app):
    at = _paste(app, SIX[:-1])                                    # Miami net income not copied yet
    text = _text(at)
    assert not at.exception
    assert "Analysing **Oct** against **Sep**" in text
    assert "Missing for Nov: Net income (Miami, total)" in text
    # ...and pasting the missing tab afterwards completes the month.
    at = _paste(at, SIX[-1:])
    assert "Analysing **Nov** against **Oct**" in _text(at)


def test_net_income_that_cannot_be_matched_asks_for_a_city(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICING_SIM_DATA", str(tmp_path / "facts.csv"))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    # The per-vehicle screen carries nothing to match on: the app asks instead of guessing.
    at.text_area(key="paste_text").set_value(
        (SAMPLES / "net_income_pvpm-miami.txt").read_bytes().decode("utf-8-sig"))
    at.run()
    assert not at.exception and len(at.selectbox) == 1
    at.selectbox[0].select("Miami").run()                         # the button is disabled until chosen
    at.button[[b.label for b in at.button].index("Import with these cities")].click()
    at.run()
    assert not at.exception and not at.selectbox


def test_copy_list_is_numbered_in_the_order_of_the_simulation_tabs(app):
    table = next(m.value for m in app.markdown if "Copy this tab" in m.value)
    rows = [r.split("|")[1:3] for r in table.splitlines()[2:]]
    assert [n.strip() for n, _ in rows] == ["1", "2", "3", "4", "5", "6"]
    assert [t.strip("* ") for _, t in rows] == ["Price history", "Market demand", "Unit sales",
                                                 "Capacity utilization", "Net income", "Net income"]
    assert "Orlando" in table.splitlines()[6] and "Miami" in table.splitlines()[7]
