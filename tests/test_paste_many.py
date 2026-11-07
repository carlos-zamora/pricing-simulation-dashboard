"""Several tables pasted into one box: splitting, recognition, city inference."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from pricing.parsers import parse_text, split_tables

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data"
FILES = sorted(SAMPLES.glob("*.txt"))


def _raw(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")      # keeps the CRLF line endings


def _key(parsed):
    return (parsed.table, len(parsed.facts), round(parsed.facts["value"].sum(), 4))


@pytest.mark.parametrize("sep", ["", "\n", "\r\n", "\n\n", "\r\n\r\n", "  \n"])
def test_all_sample_files_in_one_paste_split_back(sep):
    """Any separator (including none at all) cuts the 13 sample tables back apart."""
    texts = [_raw(f) for f in FILES]
    parts = split_tables(sep.join(texts))
    assert len(parts) == len(FILES)
    got = [_key(parse_text(p, defer_city=True)) for p in parts]
    want = [_key(parse_text(t, defer_city=True)) for t in texts]
    assert got == want


@pytest.mark.parametrize("seed", range(5))
def test_any_order_splits_the_same(seed):
    texts = [_raw(f) for f in FILES]
    random.Random(seed).shuffle(texts)
    parts = split_tables("".join(texts))
    assert [_key(parse_text(p, defer_city=True)) for p in parts] == \
           [_key(parse_text(t, defer_city=True)) for t in texts]


def test_single_table_is_returned_unchanged():
    text = _raw(SAMPLES / "price_history.txt")
    parts = split_tables(text)
    assert len(parts) == 1 and _key(parse_text(parts[0])) == _key(parse_text(text))


def test_garbage_is_not_swallowed():
    parts = split_tables("hello there\n" + _raw(SAMPLES / "price_history.txt"))
    assert len(parts) == 2 and parts[0] == "hello there"


def test_net_income_can_be_parsed_without_a_city():
    p = parse_text(_raw(SAMPLES / "net_income_total-miami.txt"), defer_city=True)
    assert p.city is None and set(p.facts["city"]) == {""}
    q = p.with_city("Miami")
    assert q.city == "Miami" and set(q.facts["city"]) == {"Miami"}


# --------------------------------------------------------------------------- #
# Store.add_pasted and net income city detection
# --------------------------------------------------------------------------- #
from pricing.store import Store, infer_net_income_city, sort_facts  # noqa: E402


def _sample_store(tmp_path):
    store = Store(tmp_path / "f.csv")
    for f in FILES:
        if not f.name.startswith("net_income"):
            store.add_text(_raw(f), label=f.name)
    return store


@pytest.mark.parametrize("city", ["Orlando", "Miami"])
def test_city_is_detected_from_the_numbers(tmp_path, city):
    store = _sample_store(tmp_path)
    p = parse_text(_raw(SAMPLES / f"net_income_total-{city.lower()}.txt"), defer_city=True)
    assert infer_net_income_city(p, store.facts) == city


@pytest.mark.parametrize("name", ["net_income_pvpm-miami.txt", "net_income_prv-orlando.txt",
                                  "net_income_percentage-orlando.txt"])
def test_city_is_not_guessed_when_nothing_matches(tmp_path, name):
    store = _sample_store(tmp_path)
    p = parse_text(_raw(SAMPLES / name), defer_city=True)
    assert infer_net_income_city(p, store.facts) is None


def test_net_income_alone_in_an_empty_store_needs_a_city(tmp_path):
    store = Store(tmp_path / "f.csv")
    rep = store.add_pasted(_raw(SAMPLES / "net_income_total-miami.txt"))
    assert len(rep.unresolved) == 1 and store.facts.empty
    rep = store.add_pasted(rep.unresolved[0], city="Miami")
    assert not rep.unresolved and set(store.facts["city"]) == {"Miami"}


@pytest.mark.parametrize("sep", ["", "\n"])
def test_one_paste_of_every_sample_equals_importing_the_files(tmp_path, sep):
    """No city is given anywhere; only the per-vehicle and % screens (nothing to match on) are left over."""
    by_file = Store(tmp_path / "a.csv")
    by_file.add_folder(SAMPLES)
    one_paste = Store(tmp_path / "b.csv")
    rep = one_paste.add_pasted(sep.join(_raw(f) for f in FILES))
    assert not rep.errors
    assert len(rep.unresolved) == 6
    kept = by_file.facts[~by_file.facts["table"].isin(
        ["net_income_pvpm", "net_income_pct", "net_income_prv"])]
    assert sort_facts(kept).equals(sort_facts(one_paste.facts))


def test_required_six_are_enough_in_any_order(tmp_path):
    """The six tabs copied each round, shuffled, with the city never stated."""
    names = ["price_history", "unit_sales", "market_demand", "capacity_utilization",
             "net_income_total-orlando", "net_income_total-miami"]
    for seed in range(4):
        random.Random(seed).shuffle(names)
        store = Store(tmp_path / f"f{seed}.csv")
        rep = store.add_pasted("".join(_raw(SAMPLES / f"{n}.txt") for n in names))
        assert not rep.errors and not rep.unresolved
        ni = store.facts[store.facts["table"].str.startswith("net_income")]
        assert set(zip(ni["table"], ni["city"])) == {("net_income_total", "Orlando"),
                                                     ("net_income_total", "Miami")}
