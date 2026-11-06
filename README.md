# Pricing Simulation Dashboard

A Streamlit app that does what `reference/Pricing_Simulation_Analysis.xlsx` does, but a new
month is a paste instead of a spreadsheet edit. Version 0.1 = **parity with the workbook**.

## Run it

```powershell
cd pricing-sim
pip install -r requirements.txt
streamlit run app.py          # opens http://localhost:8501
pytest                        # 44 tests, incl. parity against the workbook
```

First launch loads `sample_data/` (Jul–Oct) so there is something to look at.

## Each new month

1. Run the simulation, then open **Import & data**.
2. Either paste each table (the app detects which screen it is; for net income screens pick
   Orlando or Miami), **or** save the copied tables as `.txt` into `inbox/` / any folder
   (net income files need `orlando` / `miami` in the file name) and click **Import folder**.
3. Every paste contains the full history, so re-importing is safe: values merge by month,
   and any change to an *earlier* month is flagged.
4. A month shows up in the analysis once it has the required tables (price, capacity
   utilization, market demand, net income total + per rented vehicle for both cities, and
   either the day-period demand screen or unit sales).

## Layout

```
app.py                  Streamlit UI (tabs + sidebar controls + price planner)
pricing/
  parsers.py            clipboard text -> tidy facts (table, city, daypart, firm, field, month, value)
  store.py              append/merge into data/facts.csv, completeness checks
  data.py               month-indexed accessors; day-period demand fallback
  model.py              the workbook's math (slopes, bridge, what-if, break-even, unit economics)
  insights.py           readouts regenerated from the numbers
  charts.py             Plotly figures (validated palette, one axis per chart)
tests/                  parser tests, parity tests (tests/golden.json), new-month tests
tools/extract_golden.py regenerates golden.json from the workbook
sample_data/            the 13 sample pastes + demand_by_daypart.txt
reference/              the original workbook
```

## Parity notes (read before trusting a number)

- **Demand by day period** is not one of the 13 sample screens. `sample_data/demand_by_daypart.txt`
  is taken from the workbook. If you don't paste it, demand is estimated as units sold + unfilled
  orders (within ~0.1% except Miami weekend, ~4% in Oct) and the app says so.
- **Rentals** are revenue ÷ price, as in the workbook (not `unit_sales`), so they inherit the
  simulation's rounding.
- The what-if keeps the workbook's rules: slope capped at ≤ 0, utilization capped at 100%,
  each segment independent, variable cost per rental held constant.
- The **price planner** (What-if tab) is the one addition: the same what-if function driven by
  four price boxes instead of a fixed ±$6 grid.
- Florida (combined) net-income rows are not rebuilt; no analysis uses them.

## Ideas for the next iterations

- Round log: record the prices chosen and the resulting profit each round; use it as extra data.
- Capacity-bound segments (e.g. Miami weekday at 100%): the what-if never shows a price ceiling.
  Add demand/elasticity estimated from unfilled orders.
- Pool the four segments or add Comp price as a regressor; 4–5 points per segment is thin.
- Use `unit_sales` for rentals; add share-of-market (Univ vs Comp) analysis.
- Optimizer over the planner prices (scipy) and a "why this price" explanation panel.
- Export a meeting summary (PDF/Markdown).
