"""Extract the Excel workbook's calculated values into tests/golden.json and write the
'demand by day period' sample paste (the one screen the 13 sample files do not cover).

Run:  python tools/extract_golden.py
"""
from __future__ import annotations

import json
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
WB = ROOT / "reference" / "Pricing_Simulation_Analysis.xlsx"


def num(v):
    return None if isinstance(v, str) else v


def block(ws, rows, cols):
    return [[ws[f"{c}{r}"].value for c in cols] for r in rows]


def main() -> None:
    wb = openpyxl.load_workbook(WB, data_only=True)
    pvu, dvu, pa = wb["Price vs Util"], wb["Demand vs Util"], wb["Profit Analysis"]

    golden = {
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
        "whatif_case_in_workbook": pa["B37"].value,
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
    out = ROOT / "tests" / "golden.json"
    out.write_text(json.dumps(golden, indent=1))
    print("wrote", out)

    # 'Demand - Day Period' as the simulation would paste it (tab separated).
    ws = wb["Demand - Day Period"]
    lines = ["\tOrlando\t\t\tMiami\t\t\tFlorida\t\t",
             "\tDemand\t\tOrders\tDemand\t\tOrders\tDemand\t\tOrders",
             "Month\tWkdy\tWknd\tTotal\tWkdy\tWknd\tTotal\tWkdy\tWknd\tTotal"]
    for r in range(4, 8):
        vals = [ws.cell(r, c).value for c in range(1, 11)]
        lines.append("\t".join(str(int(v)) if isinstance(v, (int, float)) else str(v) for v in vals))
    path = ROOT / "sample_data" / "demand_by_daypart.txt"
    path.write_text("\r\n".join(lines), encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()
