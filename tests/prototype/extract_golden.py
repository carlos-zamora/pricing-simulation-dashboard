"""Test-only provenance: how tests/prototype_golden.json was produced.

The original Excel prototype (Pricing_Simulation_Analysis.xlsx, next to this file) is frozen and
no longer updated. The app never reads it. This script extracts the prototype's calculated
values (Jul-Oct sample data) into the JSON file the regression tests compare against.

    pip install openpyxl          # test-only; not in requirements.txt
    python tests/prototype/extract_golden.py [output.json]

By default it rewrites tests/prototype_golden.json, which should come out unchanged.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
WB = HERE / "Pricing_Simulation_Analysis.xlsx"
DEFAULT_OUT = HERE.parent / "prototype_golden.json"


def num(v):
    return None if isinstance(v, str) else v


def block(ws, rows, cols):
    return [[ws[f"{c}{r}"].value for c in cols] for r in rows]


def main(out: Path = DEFAULT_OUT) -> None:
    wb = openpyxl.load_workbook(WB, data_only=True)
    pvu, dvu, pa = wb["Price vs Util"], wb["Demand vs Util"], wb["Profit Analysis"]

    golden = {
        "_comment": "Values calculated by the Excel prototype (Jul-Oct sample data). The prototype "
                    "is frozen and no longer maintained; these numbers are regression targets "
                    "only. Do not regenerate.",
        "price_vs_util": {
            "Orlando|Weekday": [num(pvu["B15"].value), num(pvu["B16"].value)],
            "Orlando|Weekend": [num(pvu["B35"].value), num(pvu["B36"].value)],
            "Miami|Weekday": [num(pvu["B55"].value), num(pvu["B56"].value)],
            "Miami|Weekend": [num(pvu["B75"].value), num(pvu["B76"].value)],
        },
        "demand_vs_util": {   # r2, demand slope per 10K, price slope
            seg: [num(dvu[f"B{r}"].value), num(dvu[f"B{r + 1}"].value), num(dvu[f"B{r + 2}"].value)]
            for seg, r in (("Orlando|Weekday", 15), ("Orlando|Weekend", 45),
                           ("Miami|Weekday", 75), ("Miami|Weekend", 105))
        },
        "bridge": {"Orlando": [pa[f"B{r}"].value for r in range(27, 34)],
                   "Miami": [pa[f"C{r}"].value for r in range(27, 34)]},
        "whatif_case_in_prototype": pa["B37"].value,
        "whatif_slopes_used": [pa[f"H{r}"].value for r in range(40, 44)],
        "whatif_delta": {"Orlando|Weekday": block(pa, [51], "BCDEFGH")[0],
                         "Orlando|Weekend": block(pa, [56], "BCDEFGH")[0],
                         "Miami|Weekday": block(pa, [61], "BCDEFGH")[0],
                         "Miami|Weekend": block(pa, [66], "BCDEFGH")[0]},
        "grid": {"Orlando": block(pa, range(71, 78), "BCDEFGH"),
                 "Miami": block(pa, range(83, 90), "BCDEFGH")},
        "grid_best": {"Orlando": [pa["B78"].value, pa["B79"].value, pa["B80"].value],
                      "Miami": [pa["B90"].value, pa["B91"].value, pa["B92"].value]},
        "break_even": {"inputs": block(pa, range(97, 104), "BCDE"),
                       "curve": block(pa, range(106, 113), "BCDE")},
        "unit_economics": block(pa, range(117, 125), "BCDEFG"),
        "contribution": block(pa, range(129, 137), "BCDEFG"),
    }
    out.write_text(json.dumps(golden, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT)
