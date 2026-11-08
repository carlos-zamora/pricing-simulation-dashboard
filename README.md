# Pricing Simulation Dashboard

A Streamlit app for the pricing simulation: paste each month's tables, then get price/utilization
analysis, a profit bridge, a what-if planner and break-even charts.

## Run it

```powershell
cd pricing-sim
pip install -r requirements.txt
streamlit run app.py          # opens http://localhost:8501
pytest
```

First launch loads `sample_data/` (Jul–Oct) so there is something to look at.

## Each new month (under a minute)

1. Open **Import & data**. The list beside the box shows what to copy and ticks what is already in.
2. Copy these **8 tabs** and paste them one after another into the one box (any order):

   | # | Tab | Select |
   |:-:|---|---|
   | 1 | Price history | nothing to select |
   | 2 | Market demand | nothing to select |
   | 3 | Unit sales | nothing to select |
   | 4 | Fleet size | nothing to select |
   | 5 | Capacity utilization | nothing to select |
   | 6 | Market research | nothing to select |
   | 7 | Net income | City: Orlando, Format: Total |
   | 8 | Net income | City: Miami, Format: Total |

   The order follows the simulation's tabs left to right, so you can go down the list.

3. Press **Ctrl+Enter** (or click outside the box). It imports by itself: no button, no city
   question (each net income city is detected from its numbers).

Nothing else is needed. The per-rented-vehicle, per-vehicle and % screens are derived from net income
total. Fleet size is needed every month because capacity can change. If a tab is missing, a banner names it and the dashboard keeps
showing the last complete month until you paste it.

Every paste contains the full history, so re-importing is safe: values merge by month, and any
change to an *earlier* month is flagged. Saved `.txt` files and folders (`inbox/`) still work under
"Other ways to import".

## Controls

The sidebar has two selectors: **City** (Florida = Orlando + Miami, Orlando, Miami) and **Day period** (Both, Weekday, Weekend). Florida or Both shows each combination plus the combined profit. Bridge, break-even and the price suggestion are per city (both day periods). With one day period, profit is shown as that period's contribution.

The app decides everything else for you, the same way every round:

- **Comparison:** always the latest month against the previous one ("what changed last round").
  This drives the profit bridge and the break-even comparison line.
- **Starting point:** always the latest month's prices, utilization and volumes.
- **Price sensitivity:** how much utilization drops when you raise price can't be pinned down
  from a handful of months, so every projection shows **two assumptions side by side**:
  - *Cautious*: slope of utilization vs the Univ–Comp price gap alone. Price gets credit for every
    utilization change, so it matters most.
  - *Optimistic*: price slope left after removing demand. Usually much smaller, so price matters
    least.
  In both, raising price never increases utilization.

**Suggested prices** (Price planner tab) = the weekday/weekend pair with the best profit in the
*worse* of the two cases, so it holds up whichever assumption is right. If the cases disagree on
direction, the suggestion is "hold".

A day period is only moved if the data show price matters there. Where sensitivity can't be
measured (the price gap never changed, or utilization is pinned at capacity) its price is held
and the app says why, because otherwise the model would treat price as free and suggest
unlimited increases.

**Business vs Leisure** tab: Univ's share among business
and among leisure customers, plotted against the Univ–Comp price gap. A steeper (more negative)
slope means those customers switch to Comp more readily when we charge more. On the sample data,
Orlando weekday leisure share drops about 1.0 point per +$1 and business share about 0.2. Miami
can't be measured: weekday Univ was sold out, and the weekend gap never changed. This is a readout
only. The price suggestion doesn't use it.

## Layout

```
app.py                  Streamlit UI (tabs, price planner)
pricing/
  parsers.py            clipboard text -> tidy facts (table, city, daypart, firm, field, month, value)
  store.py              merge into data/facts.csv, completeness checks
  data.py               month-indexed accessors; derived demand
  model.py              slopes, profit bridge, what-if, break-even, unit economics
  insights.py           readouts regenerated from the numbers
  charts.py             Plotly figures
tests/                  parser, regression, new-month and guard tests
  prototype_golden.json frozen expected values from an earlier prototype (no longer maintained)
  prototype/            test-only: the original spreadsheet and the script that produced the
                        golden file. The app never reads it, and a test enforces that.
sample_data/            sample pastes (Jul–Oct)
```

## Modelling notes

- **Demand per day period** = units sold + unfilled orders. Unfilled orders are reported for the
  whole city, so they are assigned to the more utilised day period. Unit sales are rounded to
  thousands, so expect about ±0.5%.
- **Rentals** = revenue ÷ price, so they inherit the simulation's rounding.
- **What-if rules**: slope capped at ≤ 0, utilization capped at 100%, each segment independent,
  variable cost per rental held constant.
- With 4–5 months per segment, treat every slope as directional.

## Ideas for the next iterations

- Round log: record the prices chosen and the resulting profit each round; use it as extra data.
- Capacity-bound segments (e.g. Miami weekday at 100%): the what-if never shows a price ceiling.
  Estimate demand/elasticity from unfilled orders.
- Pool the four segments or add Comp price as a regressor.
- Use `unit_sales` for rentals; add share-of-market (Univ vs Comp) analysis.
- Optimizer over the planner prices (scipy) and a "why this price" explanation panel.
- Export a meeting summary (PDF/Markdown).
