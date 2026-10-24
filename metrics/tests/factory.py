"""A synthetic company with simple, known numbers, so every expected metric can be worked out by
hand in the tests. Quarter index i = 0 is 2013Q1 and i = 23 is 2018Q4 (fiscal year = calendar year).

Defaults: revenue 100 + 10i; operating income 20 + i; operating cash flow 30 + 3i; capex 10; D&A 5;
interest 2; income tax 2; pre-tax income = operating income - 2; current assets 200 + i;
current liabilities 100; cash 50; equity 500 + 10i; long-term debt 100; short-term debt 20.
"""
from __future__ import annotations

from datetime import date

from store import queries
from store.queries import InMemoryBackend

QUARTER_ENDS = [(3, 31), (6, 30), (9, 30), (12, 31)]
QUARTER_STARTS = [(1, 1), (4, 1), (7, 1), (10, 1)]
FILED = [(5, 5), (8, 5), (11, 5), (2, 20)]       # Q1, Q2, Q3 10-Qs, then the 10-K in February
FIRST_YEAR = 2013

DEFAULTS = dict(
    revenue=lambda i: 100 + 10 * i,
    operating_income=lambda i: 20 + i,
    op_cash_flow=lambda i: 30 + 3 * i,
    capex=lambda i: 10,
    depreciation_amortization=lambda i: 5,
    interest_expense=lambda i: 2,
    income_tax_expense=lambda i: 2,
    pretax_income=lambda i: 18 + i,
    dividends_paid=None,                          # None: the company never paid a dividend
    current_assets=lambda i: 200 + i,
    current_liabilities=lambda i: 100,
    cash=lambda i: 50,
    equity=lambda i: 500 + 10 * i,
    long_term_debt=lambda i: 100,
    short_term_debt=lambda i: 20,
)
INCOME = ("revenue", "operating_income", "interest_expense", "income_tax_expense", "pretax_income")
INCOME_WITH_YTD = ("revenue",)                    # the others rely on the FY - (Q1+Q2+Q3) fallback
CASH_FLOW = ("op_cash_flow", "capex", "depreciation_amortization", "dividends_paid")
BALANCE = ("current_assets", "current_liabilities", "cash", "equity", "long_term_debt", "short_term_debt")


def accession(year: int, k: int) -> str:
    return f"ACC-{year}-Q{k + 1}" if k < 3 else f"ACC-{year}-FY"


def filed(year: int, k: int) -> date:
    m, d = FILED[k]
    return date(year + 1 if k == 3 else year, m, d)


def _fact(company, concept, value, start, end, year, k, tag=None):
    return dict(company_id=company, concept=concept, value=float(value), unit="USD", period_start=start,
                period_end=end, fiscal_year=year, fiscal_period=f"Q{k + 1}" if k < 3 else "FY",
                form="10-Q" if k < 3 else "10-K", accession=accession(year, k), filed_date=filed(year, k),
                source_tag=tag)


def build_facts(company="anon_001", years=6, skip_quarters=(), **overrides):
    fns = {**DEFAULTS, **overrides}
    facts = []
    for y in range(FIRST_YEAR, FIRST_YEAR + years):
        for concept, fn in fns.items():
            if fn is None:
                continue
            vals = [fn((y - FIRST_YEAR) * 4 + k) for k in range(4)]
            ends = [date(y, *QUARTER_ENDS[k]) for k in range(4)]
            starts = [date(y, *QUARTER_STARTS[k]) for k in range(4)]
            if concept in BALANCE:
                tag = {"long_term_debt": "LongTermDebtNoncurrent", "short_term_debt": "DebtCurrent"}.get(concept)
                for k in range(4):
                    if (y - FIRST_YEAR) * 4 + k in skip_quarters:
                        continue
                    facts.append(_fact(company, concept, vals[k], None, ends[k], y, k, tag))
            elif concept in INCOME:
                for k in range(3):                 # Q1..Q3 reported as 3-month figures
                    if (y - FIRST_YEAR) * 4 + k in skip_quarters:
                        continue
                    facts.append(_fact(company, concept, vals[k], starts[k], ends[k], y, k))
                if concept in INCOME_WITH_YTD:     # a 10-Q also shows year to date
                    facts.append(_fact(company, concept, sum(vals[:2]), starts[0], ends[1], y, 1))
                    facts.append(_fact(company, concept, sum(vals[:3]), starts[0], ends[2], y, 2))
                facts.append(_fact(company, concept, sum(vals), starts[0], ends[3], y, 3))  # the 10-K: full year
            else:                                  # cash flow: year to date only
                for k in range(4):
                    if (y - FIRST_YEAR) * 4 + k in skip_quarters:
                        continue
                    facts.append(_fact(company, concept, sum(vals[:k + 1]), starts[0], ends[k], y, k))
    return facts


def all_accessions(facts) -> set[str]:
    return {f["accession"] for f in facts}


def gdp_value(j: int) -> float:
    """Quarterly real GDP index, j = 0 at 2013-01-01. Growth varies so a beta can be estimated."""
    return 1000 * (1 + 0.004 * j + 0.0003 * j * j)


def build_macro(quarters=24, revision=None):
    rows = []
    for j in range(quarters):
        y, q = FIRST_YEAR + j // 4, j % 4
        obs = date(y, 3 * q + 1, 1)
        pub_month = 3 * q + 4                      # published about a month after the quarter ends
        vint = date(y + pub_month // 13, (pub_month - 1) % 12 + 1, 28)
        rows.append(dict(series_id="GDPC1", value=gdp_value(j), obs_date=obs, vintage_date=vint))
    if revision:
        rows.append(revision)
    rows += [
        dict(series_id="UNRATE", value=3.9, obs_date=date(2018, 12, 1), vintage_date=date(2019, 1, 4)),
        dict(series_id="UNRATE", value=4.2, obs_date=date(2019, 1, 1), vintage_date=date(2019, 2, 1)),
        dict(series_id="T10Y2Y", value=0.25, obs_date=date(2019, 2, 28), vintage_date=date(2019, 2, 28)),
        dict(series_id="BAA10Y", value=1.9, obs_date=date(2019, 2, 28), vintage_date=date(2019, 2, 28)),
    ]
    return rows


def install(facts=None, events=None, macro=None):
    queries.set_backend(InMemoryBackend(facts=facts or [], events=events or [], macro=macro or []))


def reset():
    queries.set_backend(InMemoryBackend())
