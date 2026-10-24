"""Data quality: does each company have what the MVP metrics need? (metrics/SPEC.md)

`coverage` is read-only SQL over `facts`. A company that lacks a REQUIRED concept cannot get the
metrics for the Fundamentals, Risk and Scenarios agents, so it is a candidate to drop from the
universe (CLAUDE.md: drop companies that do not map cleanly).
"""
from __future__ import annotations

from datetime import date

import psycopg

from store.concepts import COMPOSITES

# Needed by the MVP metrics for essentially every operating company. Absence is a data problem.
REQUIRED = ("revenue", "operating_income", "op_cash_flow", "capex", "depreciation_amortization",
            "current_assets", "current_liabilities", "cash", "equity", "income_tax_expense", "pretax_income")
# Concepts a filer may report only as parts (store.concepts.COMPOSITES): present if every component is.
# Companies with no usable operating income in the replay era (2018 to 2024). The metrics engine leaves
# operating_income missing for them rather than approximating it (pretax income plus interest would include
# non-operating items), so their Fundamentals bundles are unusable and the Fundamentals outcome rule returns
# `unresolvable`. Value = "TICKER: why". Decided with the drop-candidate review.
_NO_LINE = "no OperatingIncomeLoss line in its filings"
OPERATING_INCOME_EXEMPT = {
    "anon_001": f"COP: {_NO_LINE}",
    "anon_003": f"MRK: {_NO_LINE}",
    "anon_009": f"NKE: {_NO_LINE}",
    "anon_026": f"XOM: {_NO_LINE}",
    "anon_028": f"NUE: {_NO_LINE}",
    "anon_037": f"PFE: {_NO_LINE}",
    "anon_049": f"LLY: {_NO_LINE}",
    "anon_008": "HON: tags OperatingIncomeLoss only from 2021, and its annual figure first appears in a 10-K filed "
                "in 2025, so nothing usable existed point in time before then",
    "anon_044": "JNJ: reports pretax income but no operating income line",
    "anon_048": "GE: its operating income tag stops in 2014",
}
# Companies kept in the universe despite a data gap, so the report names the gap instead of recommending a drop.
# Decided at the drop-candidate review: the gap is real and accepted. Their bundles carry fewer metrics.
KNOWN_GAPS = {
    "anon_006": "MCD: no pretax income total; domestic and foreign parts are reported only annually, so "
                "pretax_income, roic and debt_to_ebitda are missing",
    "anon_031": "NVDA: annual capex first appears in 10-Ks filed from 2024 (the original 10-Ks have no such fact), so "
                "Q4 capex cannot be derived point in time and every fcf metric is missing until then",
    "anon_016": "MSFT: no depreciation_amortization total and its parts are mostly annual, so "
                "debt_to_ebitda is missing in the early years",
}
# Known gaps that the existence-based coverage check cannot see (the concept exists, just not for the replay
# years), so they are listed even though `ok` is true.
PERIOD_GAPS = {"anon_031"}
# Parts only count when they are reported often enough to build quarters (about 10 years of filings).
# MSFT and MCD tag their parts once a year (11 to 29 facts), which cannot give a quarter.
COMPOSITE_MIN_FACTS = 40
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
        exempt = ["operating_income"] if company_id in OPERATING_INCOME_EXEMPT else []
        missing = [c for c in REQUIRED if c not in have and c not in exempt
                   and not (c in COMPOSITES and all(p in have and have[p][0] >= COMPOSITE_MIN_FACTS
                                                    for p in COMPOSITES[c]))]
        rev = have.get("revenue")
        limit = SHORT_HISTORY_MAX_START if company_id in short else HISTORY_NEEDED_FROM
        shallow = bool(rev) and rev[1] > limit
        out.append({
            "company_id": company_id,
            "missing_required": missing,
            "exempt": exempt,
            "exempt_reason": OPERATING_INCOME_EXEMPT.get(company_id),
            "missing_optional": [c for c in OPTIONAL if c not in have],
            "revenue_first_period": rev[1] if rev else None,
            "revenue_last_period": rev[2] if rev else None,
            "history_too_short": shallow,
            "ok": not missing and not shallow,
            "known_gap": KNOWN_GAPS.get(company_id),
        })
    return out


def drop_candidates(report: list[dict]) -> list[str]:
    """Companies with a gap nobody has accepted. Accepted ones (KNOWN_GAPS) are listed by `known_gaps`."""
    return [r["company_id"] for r in report if not r["ok"] and not r["known_gap"]]


def known_gaps(report: list[dict]) -> dict[str, str]:
    """Accepted gaps that are still really there (a gap that has since been fixed drops off the list)."""
    return {r["company_id"]: r["known_gap"] for r in report
            if r["known_gap"] and (not r["ok"] or r["company_id"] in PERIOD_GAPS)}
