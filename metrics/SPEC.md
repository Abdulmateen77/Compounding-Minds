# Metrics spec (Person A)

Exactly how each number an agent sees is computed. The metric names are a contract: they match
`store/stubs/metrics_*.json`, the rules in `principles/*.md`, and `store/concepts.py::METRIC_INPUTS`
(a test keeps those three in sync). Python computes every number. No LLM touches this layer.

Every metric returns `{name, value, unit, as_of, inputs: [accession, ...]}`. `inputs` is every filing
the value was computed from, so any number in a prompt traces back to a filing.

## 1. Rules that apply to every metric

**Visibility.** Every input is read through `store/queries.py` at `as_of`. Nothing else reads tables.

**Discrete quarters.** Agents reason in quarters, but filings report differently:

| Statement | What a 10-Q reports | Discrete quarter Q |
|---|---|---|
| Income statement (revenue, operating income, interest, tax) | 3-month and year-to-date facts | Use the 3-month fact (period of 80 to 100 days) |
| Cash flow (operating cash flow, capex, D&A, dividends) | Year-to-date only: 3, 6, 9 months | Q1 = 3M. Q2 = 6M - 3M. Q3 = 9M - 6M |
| Q4 of any flow | Not reported. Only the full year in the 10-K | Q4 = FY - 9M year-to-date, available from the 10-K's `filed_date` |
| Balance sheet (cash, debt, assets) | Value at period end | Use directly |

A derived quarter becomes visible at the **later** of the filing dates of the facts it uses. So Q4 appears
when the 10-K is filed, never at the quarter's end. When subtracting, take both values from the same
accession if it has them, otherwise the latest visible row for each (a restatement can otherwise create
a fake jump).

**TTM** = sum of the last 4 discrete quarters. **Latest quarter (Q0)** = the most recent period end visible
at `as_of`. Q-1, Q-2 ... are the quarters before it. Prompts only ever say Q0, Q-1 and so on.

**Missing data.** If a metric's inputs are not all visible, the metric is left out of the bundle and its
name goes in `missing`. A company with 3 or more missing metrics at an `as_of` is skipped for that agent and
quarter, and the skip is logged. A metric is never filled with a guess.

**Units.** Ratios are fractions (0.142, not 14.2). Multiples are `x`. Counts are `count`. Rates from FRED are
divided by 100 so 3.6% is 0.036.

## 2. Fundamentals (Buffett)

| Metric | Unit | Formula |
|---|---|---|
| `fcf_margin_ttm` | ratio | (TTM op_cash_flow - TTM capex) / TTM revenue |
| `fcf_margin_qoq_change` | ratio | `fcf_margin_ttm` at Q0 minus `fcf_margin_ttm` at Q-1 (TTM, so it is not swamped by one noisy quarter) |
| `operating_margin` | ratio | TTM operating_income / TTM revenue |
| `roic` | ratio | NOPAT / invested capital. NOPAT = TTM operating_income x (1 - tax rate). Tax rate = TTM income_tax_expense / TTM pretax_income, clamped to 0 to 0.35. Invested capital = equity + long_term_debt + short_term_debt - cash, averaged over Q0 and Q-4 |
| `debt_to_ebitda` | x | (long_term_debt + short_term_debt) / (TTM operating_income + TTM depreciation_amortization). If EBITDA <= 0 the metric is capped at 99 |
| `fcf_slope_8q` | ratio/q | OLS slope of discrete-quarter FCF margin over the last 8 quarters |
| `capex_to_revenue` | ratio | TTM capex / TTM revenue |

## 3. Risk (Munger)

| Metric | Unit | Formula |
|---|---|---|
| `interest_coverage` | x | TTM operating_income / TTM interest_expense. No interest expense: capped at 99 |
| `current_ratio` | x | current_assets / current_liabilities at Q0 |
| `cash_runway_quarters` | q | If average FCF of the last 4 quarters is negative: cash / its absolute value. Otherwise 40 (not burning cash) |
| `dividend_cut_history_5y` | count | Number of year-over-year falls of 25% or more in TTM dividends_paid, checked each quarter over the last 5 years. `dividends_per_share` is the cross-check when present |
| `auditor_changes_5y` | count | Number of 8-K filings with item 4.01 in the last 5 years (events table) |
| `going_concern_hits` | count | Going-concern passages in 10-K and 10-Q filings filed in the last 4 quarters (events table, from the event extractor) |
| `leverage_trend_8q` | x/q | OLS slope of `debt_to_ebitda` over the last 8 quarters |

## 4. Scenarios (Dalio)

| Metric | Unit | Formula |
|---|---|---|
| `revenue_growth_yoy` | ratio | Q0 revenue / revenue of the same quarter a year earlier - 1 |
| `revenue_growth_mean_5y` | ratio | Mean of the last 20 quarterly year-over-year revenue growth values |
| `revenue_growth_std_5y` | ratio | Standard deviation of the same 20 values |
| `revenue_macro_beta` | x | OLS slope of quarterly revenue growth on `gdp_growth_yoy` over the last 20 quarters. Needs at least 12 points |
| `gdp_growth_yoy` | ratio | Latest GDPC1 value visible at `as_of` (ALFRED vintage) over the value 4 quarters earlier - 1 |
| `unemployment_rate` | ratio | Latest UNRATE visible at `as_of` (ALFRED vintage) / 100 |
| `yield_curve_10y_2y` | ratio | Latest T10Y2Y observation on or before `as_of` / 100 |
| `credit_spread_baa` | ratio | Latest BAA10Y observation on or before `as_of` / 100 |

Macro series: revised ones (GDP, unemployment) must use ALFRED vintages so we see what was known then.
Market rates are never revised, so `vintage_date = obs_date`. See `store/concepts.py::MACRO_SERIES`.

## 5. Stretch agents

| Metric | Agent | Formula |
|---|---|---|
| `gross_margin` | Moat | TTM gross_profit / TTM revenue. If gross_profit is missing: (revenue - cost_of_revenue) / revenue |
| `gross_margin_std_4q` | Moat | Standard deviation of discrete-quarter gross margin over 4 quarters |
| `rnd_intensity`, `sga_intensity` | Moat | TTM rnd_expense / revenue, TTM sga_expense / revenue |
| `reverse_dcf_implied_growth` | Valuation | Open decision: needs a market value, but prices are defined as context only |

## 6. Tests this spec needs (Phase 3)

1. Hand-computed fixtures: one company, 10 quarters of fake facts, every metric checked to 6 places.
2. Discrete-quarter derivation: Q2 from 6M - 3M, Q4 from FY - 9M, and Q4 invisible before the 10-K date.
3. A restatement: the metric at a date before the restatement uses the old value, after it the new one.
4. Traceability: every accession in `inputs` exists in `facts` for that company.
5. Missing data: a missing input drops the metric and lists it in `missing`. It is never guessed.
