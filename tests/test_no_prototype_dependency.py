"""The Excel prototype is frozen. Nothing the app runs may read it or depend on Excel."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = [ROOT / "app.py", *sorted((ROOT / "pricing").glob("*.py"))]
FORBIDDEN = re.compile(r"xlsx|openpyxl|excel|workbook", re.IGNORECASE)


def test_runtime_code_never_references_the_prototype():
    hits = [f"{f.relative_to(ROOT)}:{i}: {line.strip()}"
            for f in RUNTIME for i, line in enumerate(f.read_text().splitlines(), 1)
            if FORBIDDEN.search(line)]
    assert not hits, "\n".join(hits)


def test_requirements_do_not_need_excel_libraries():
    assert "openpyxl" not in (ROOT / "requirements.txt").read_text().lower()
