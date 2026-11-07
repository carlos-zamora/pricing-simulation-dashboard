# CLAUDE.md

Streamlit dashboard for a team pricing simulation (IESE EMBA, marketing management). Each month the
user pastes the simulation's tables; the app shows company performance and helps the team choose
next month's weekday/weekend prices in Orlando and Miami. Used live in team meetings, so speed and
clarity matter more than feature count.

See `README.md` for the user-facing description. This file is for working on the code.

## Commands (Windows / PowerShell)

```powershell
pip install -r requirements.txt
streamlit run app.py        # http://localhost:8501
pytest                      # whole suite, about 6 s (52 tests at last count)
pytest tests/test_price_guide.py -q    # one file while iterating
```

- Needs a recent Streamlit (charts use `width="stretch"`). Developed on Streamlit 1.67, Plotly 7, pandas 3.
- First launch with no `data/facts.csv` loads `sample_data/` (Jul–Oct) so the app is never empty.
- Run `pytest` before finishing any task. Tests must pass without the real `data/facts.csv`.

## Hard rules (the user asked for these explicitly)

1. **Nothing in the app may depend on the Excel prototype.** `tests/test_no_prototype_dependency.py`
   greps `app.py` and `pricing/*.py` for `xlsx|openpyxl|excel|workbook`. Do not mention them, even in
   comments or docstrings. `tests/prototype/` (the xlsx and `extract_golden.py`) is test-only
   provenance: **never delete it**, never import it from app code, and don't add `openpyxl` to
   `requirements.txt`.
2. **Import must stay copy/paste simple.** The user has almost no time mid-simulation. Do not add
   mandatory manual steps or screens (a day-period demand paste was already rejected as too much work).
   Any new input must come from tables the simulation already copies to the clipboard.
3. **Only two controls: city and day period.** They are sidebar radios (`city_sel`: Florida / Orlando / Miami,
   `daypart_sel`: Both / Weekday / Weekend; default Florida + Both). Florida = both cities. The base-month /
   focus-month / sensitivity-case selectors were removed on purpose: the app compares the latest month with
   the previous one and shows both sensitivity assumptions side by side. Don't add other selectors; if
   something needs a choice, show both outcomes instead. (The only allowed selectbox is the city picker
   when pasting a net income table.) Everything is computed for all segments; `config.scope()` filters at
   render time. Bridge, break-even, heatmap and price guide are city-level (both day periods), so with one
   day period selected they show a note saying so. With one day period, profit figures are that period's
   contribution (pre-tax profit is only reported per city): `model.scope_performance`.
4. **Never recommend a price the data can't support.** A day period whose price sensitivity is
   unmeasurable is *held* and explained, not optimized (see "Price guide" below).
5. **Chart conventions**
   - Every best-fit line shows its slope in a legend (`charts.scatter_with_fit`: "Best fit / slope ± x unit / R² y").
   - No dual axes: use small multiples or indexed series.
   - Legend whenever there are 2+ series; hairline grids; colors from the palette in `charts.py`
     (Univ blue, Comp orange, aqua, magenta), assigned in fixed order. Text never uses the series color.
   - Use newlines (bullet lists, `<br>` in Plotly text, line breaks in `help=` tooltips) to separate
     separate insights or values. The user finds dense single paragraphs hard to read.
6. **Don't commit user data.** `data/facts.csv` and `data/_test_facts.csv` are git-ignored. Never
   overwrite `data/facts.csv` when making changes.

## Architecture

```
app.py                  Streamlit UI only: tabs, widgets, layout. No modelling logic.
pricing/
  config.py             Constants: month order (Jul first), cities, dayparts, required/optional tables
  parsers.py            clipboard text -> tidy facts. detect_kind(), parse_text(), parse_number()
  store.py              Store: merge facts into data/facts.csv, coverage, complete_months(), ImportReport
  data.py               SimData: month-indexed accessors (price, utilization, demand, net, rentals...)
  model.py              All numbers: regressions, profit bridge, what-if, price guide, break-even
  insights.py           Plain-language readouts generated from the numbers (lists of short strings)
  charts.py             Plotly figures only; no data wrangling beyond what a chart needs
tests/                  pytest; see "Tests" below
sample_data/            13 real clipboard pastes (Jul–Oct) used by tests and first launch
inbox/                  default folder for the "Import folder" button
```

Data flow: `paste/file -> parsers -> Store (data/facts.csv) -> SimData -> model -> insights/charts -> app.py`.
Keep that direction. `app.py` calls `model`/`insights`/`charts`; those never import `app`.

### Storage: tidy facts

One row per number: `table, city, daypart, firm, field, month, value` in `data/facts.csv`.
- Re-importing is safe: `merge_facts` keys on all columns except `value`, the new value wins, and
  changes to earlier months are reported (the simulation can restate history).
- A month shows up in the analysis only when every table in `config.REQUIRED_TABLES` is present for it
  (`Store.complete_months()`).
- Adding a table type means: `config.py` (REQUIRED or OPTIONAL), `parsers.detect_kind` + parsing,
  a `SimData` accessor, a sample file in `sample_data/`, and a parser test.

### Clipboard format (parsers)

Tab-separated, CRLF line endings, no trailing newline, multi-row merged headers (forward-filled),
values with `$`, `%`, thousands commas, float noise like `32700.000000000004` (rounded to 9 d.p.).
Net income screens are transposed and carry no city, so the city comes from the UI selectbox or the
file name (`orlando` / `miami`); the basis (total / per vehicle per month / per rented vehicle / %)
is auto-detected. Parser changes must keep all 13 files in `sample_data/` parsing (`test_parsers.py`).

## Modelling notes you need before touching `model.py`

- **Rentals** = revenue ÷ price (inherits simulation rounding).
- **Demand per day period** = units sold (Univ + Comp) + unfilled orders. Unfilled orders are reported
  per city, so they go to the busier (higher-utilization) day period. Accurate to about ±0.5%.
- **Two price-sensitivity assumptions** (slope = utilization points per +$1):
  - *Cautious* (`CASE_GAP_ONLY`): regress utilization on the Univ–Comp price gap alone. Price gets
    credit for all utilization movement, so price matters most.
  - *Optimistic* (`CASE_DEMAND_ADJ`): two steps (`demand_vs_util`): regress utilization on demand,
    then regress the leftover (residual) on the price gap; use that second slope. Price matters least.
- **What-if** (`WhatIfSegment.respond`): utilization = util0 + slope/100 × Δprice, clamped to 0–1;
  slope capped at ≤ 0 (raising price never raises utilization); rentals scale with utilization;
  variable cost per rental held constant; each segment independent. Only our price moves; the
  competitor's price is held, while the slope was fitted on the *gap*.
- **Price guide** (`price_guide`): evaluates a 7×7 weekday × weekend grid (deltas −6..+6 around the
  latest prices), takes the cell-by-cell worse of the two cases, and picks the best cell (maximin).
  A day period with cautious slope ≥ 0 is *unmeasurable* (the gap never changed, or utilization is
  pinned at capacity so the regression has the wrong sign): its price is held and its grid cells are
  blank (NaN). Without this, both cases treat price as free and the model suggests unlimited increases.
- With only 4–5 months per segment every slope is directional. The UI says so; keep saying so.

### What the sample data currently says (useful as a sanity check after changes)

- Orlando: hold at $41 weekday / $34 weekend (worst-case profit $2.15M). Cautious says cut, optimistic says raise.
- Miami: no recommendation. Weekday is at 100% utilization with about 64,000 unfilled orders (about 10% of demand);
  weekend price gap never changed.

## Tests

- `test_parsers.py`: number parsing, kind detection, net-income basis detection, merge idempotence.
- `test_parity.py`: compares the model with `tests/prototype_golden.json`, a **frozen** snapshot of the
  old spreadsheet's results. Exact match for most stats; demand-based stats use tolerances because
  demand is now derived (Miami weekend Oct differs about 4%, so its demand-slope tolerance is 1.5). The golden
  file is no longer maintained: if you deliberately change the maths, update the expected values and
  say why in the commit message, don't loosen tolerances silently.
- `test_new_month.py`: simulates importing a new month end to end.
- `test_price_guide.py`: worst case ≤ both cases; Orlando hold at 41/34; Miami unmeasurable and
  no recommendation; agreeing cases pick the best cell.
- `test_app_smoke.py`: Streamlit `AppTest` headless run: sidebar has only the two radios, every city x day-period combination runs, "Analysing **Oct** against **Sep**",
  "no price recommendation" shown.
- `test_no_prototype_dependency.py`: the guard in rule 1.
- Tests that need a store use `data/_test_facts.csv`, never `facts.csv`.
- New behaviour gets a test in the matching file; UI-only layout changes need a screenshot check instead (below).

## Verifying UI changes

`AppTest` only proves the app runs. For layout work, run the app and look at it (Playwright screenshot
or the browser). Check: legend placement, text clipped at chart edges, subplot titles colliding,
legends truncated in narrow three-column rows (legends sit below the plot at height 430), and that a
`$0` delta doesn't render a green arrow (`delta_color="off"`).

## Working style for this repo

- Work in small tasks: one behaviour per change, tests passing, then stop. Don't refactor unrelated code.
- Prefer putting logic in `model.py`/`insights.py` with a test, and keeping `app.py` thin.
- Readouts in `insights.py` return `list[str]` (one finding per string) and are rendered with `bullets()`/`nested()`.
- Keep wording plain: this is read aloud in a team meeting. Show the number next to its interpretation.
- Don't claim the model is right. Where evidence is thin, say what can't be measured.
- Git: commit only when asked. Keep commits small and describe the user-visible effect.

## Task backlog (each item is sized for one Claude Code session)

Pick one, do it, run `pytest`, stop. "Done when" is the acceptance check.

1. **Round log.** Persist the prices chosen and resulting profit each round (`data/rounds.csv`, git-ignored),
   shown as a small table on the Overview tab. *Done when:* a round can be recorded in two clicks and
   survives a restart; test for load/save.
2. **Merge the two regression tabs** ("Price vs Utilization" and "Demand vs Utilization") into one
   "Diagnostics" tab. *Done when:* same charts and readouts, one tab, smoke test updated.
3. **Capacity-bound segments** (e.g. Miami weekday at 100%): estimate how much price can rise using
   unfilled orders as the unmet-demand signal, to give a bounded test step instead of "unknown".
   *Done when:* Miami weekday shows a suggested small step with the reasoning; clearly labelled as an
   assumption; tests cover the capacity-bound branch.
4. **Pooling / extra regressors.** Pool the four segments or add the competitor's price as a regressor
   so Miami weekend becomes measurable. *Done when:* a documented comparison of fit quality on the
   sample data, and the price guide uses it only if it beats the current approach.
5. **Use `unit_sales` for rentals** instead of revenue ÷ price. *Done when:* rentals differ only by
   rounding, parity tests still pass or are updated with a stated reason.
6. **Share of market** (Univ vs Comp) analysis from the existing unit sales and demand tables.
7. **Optimizer** over the planner prices (scipy or finer grid) plus a "why this price" panel.
   Keep the maximin rule unless the user approves a change.
8. **Export a meeting summary** (Markdown/PDF): prices chosen, expected profit under both cases, caveats.
9. **Per-month import checklist**: show which required tables are still missing for the newest month
   directly on the Overview tab, not only in Import & data.

## Gotchas

- `MONTH_ORDER` starts in July; month sorting must use it, never alphabetical order.
- Streamlit reruns the whole script on every interaction; `Store` lives in `st.session_state`.
  After import, `finish_import` saves and calls `st.rerun()`.
- Number-input state for the planner is keyed `plan_{latest}_{segment}`; the "Fill with suggested prices"
  button writes to those keys through a callback (writing after the widget renders raises an error).
- `linfit` returns `None` for undefined slopes (constant x). Callers must handle `None`, not assume a float.
- Don't assume Orlando and Miami have the same measurable segments; loop over `SEGMENTS`.
- The user's machine is Windows with OneDrive paths containing spaces; quote paths in any command you give.
