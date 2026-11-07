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
