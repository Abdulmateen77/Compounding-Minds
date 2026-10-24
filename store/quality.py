"""Data quality: does each company have what the MVP metrics need? (metrics/SPEC.md)

`coverage` is read-only SQL over `facts`. A company that lacks a REQUIRED concept cannot get the
metrics for the Fundamentals, Risk and Scenarios agents, so it is a candidate to drop from the
universe (CLAUDE.md: drop companies that do not map cleanly).
"""
from __future__ import annotations

from datetime import date

import psycopg

# Needed by the MVP metrics for essentially every operating company. Absence is a data problem.
REQUIRED = ("revenue", "operating_income", "op_cash_flow", "capex", "depreciation_amortization",
            "current_assets", "current_liabilities", "cash", "equity", "income_tax_expense", "pretax_income")
# Legitimately absent for some companies (no dividends, no interest expense, no short-term debt).
OPTIONAL = ("dividends_paid", "dividends_per_share", "interest_expense", "long_term_debt", "short_term_debt")
# 5-year statistics at the first replay quarter (2018Q1) need revenue back to about 2013.
HISTORY_NEEDED_FROM = date(2013, 12, 31)
# A recent filer (flagged short_history in universe.json) only needs to start by here: its calls
# begin when enough quarters exist, and the replay skips quarters with too many missing metrics.
SHORT_HISTORY_MAX_START = date(2021, 12, 31)


def coverage(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""SELECT company_id, concept, count(*), min(period_end), max(period_end)
                       FROM facts GROUP BY company_id, concept""")
        rows = cur.fetchall()
        cur.execute("SELECT company_id, short_history FROM companies ORDER BY company_id")
        company_rows = cur.fetchall()
    ids = [r[0] for r in company_rows]
    short = {r[0] for r in company_rows if r[1]}
    by_company: dict[str, dict[str, tuple]] = {i: {} for i in ids}
    for company_id, concept, n, lo, hi in rows:
        by_company.setdefault(company_id, {})[concept] = (n, lo, hi)
    out = []
    for company_id in ids:
        have = by_company[company_id]
        missing = [c for c in REQUIRED if c not in have]
        rev = have.get("revenue")
        limit = SHORT_HISTORY_MAX_START if company_id in short else HISTORY_NEEDED_FROM
        shallow = bool(rev) and rev[1] > limit
        out.append({
            "company_id": company_id,
            "missing_required": missing,
            "missing_optional": [c for c in OPTIONAL if c not in have],
            "revenue_first_period": rev[1] if rev else None,
            "revenue_last_period": rev[2] if rev else None,
            "history_too_short": shallow,
            "ok": not missing and not shallow,
        })
    return out


def drop_candidates(report: list[dict]) -> list[str]:
    return [r["company_id"] for r in report if not r["ok"]]
