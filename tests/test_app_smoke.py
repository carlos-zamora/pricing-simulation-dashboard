"""Headless run of the Streamlit app on the sample data."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_app_runs_without_controls_and_compares_latest_to_previous_month():
    data_file = ROOT / "data" / "facts.csv"
    existed = data_file.exists()
    try:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
        assert not at.exception
        assert not at.sidebar.selectbox and not at.sidebar.radio      # nothing to configure
        assert not at.selectbox                                        # (city picker appears only on paste)
        text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
        assert "Analysing **Oct** against **Sep**" in text
        assert "no price recommendation" in text                       # Miami explained, not hidden
    finally:
        if not existed and data_file.exists():
            data_file.unlink()
