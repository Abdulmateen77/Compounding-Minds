"""Fundamentals and Scenarios outcome rules (README 7.1, 8.2). Pure Python, no LLM.

Both read facts only through store.queries and only look at filings made AFTER `as_of`.

fcf_margin_improves_next_q
    Q0 = latest quarter visible at as_of for which every input has a TTM. Q1 = the next
    quarter, the first one filed after as_of (10-Q, or the 10-K for Q4). yes iff BOTH
    fcf_margin_ttm and operating_margin (TTM, metrics/SPEC.md section 2) are strictly higher at
    Q1 than at Q0. TTM matches what the agent was shown, so one noisy quarter or seasonality does
    not decide the call. resolution_date = filing date of Q1.

revenue_bucket_next_4q
    growth = (revenue of the next 4 quarters) / (revenue of the 4 quarters ending Q0) - 1,
    bucketed with grader/config.py BUCKETS. resolution_date = filing date of the 4th quarter.

Restatements: all values are read AS KNOWN ON THE RESOLUTION DATE. Q0 and Q1 come from the same
view, so a restated Q0 (comparatives restated in the Q1 filing) is compared like for like and a
restatement filed after the resolution date is ignored. This is also what the store's
"latest row with filed_date <= t" rule gives. Choice documented in grader/README section in
README 8.2.

Anything missing (concept never tagged, next filing not visible by the deadline, trailing
revenue <= 0) returns `unresolvable` with a reason; it is excluded from accuracy, never wrong.
"""
from __future__ import annotations

from datetime import date, timedelta

from schemas import AgentCall
from store import queries  # noqa: F401  (backend is set on store.queries)

from .config import FUNDAMENTALS_RESOLUTION_DAYS, SCENARIOS_RESOLUTION_DAYS
from .facts import Quarter, common_ends, quarter_table, run_ending_at, ttm
from .scoring import bucket_for_growth

FUNDAMENTALS_Q = "fcf_margin_improves_next_q"
SCENARIOS_Q = "revenue_bucket_next_4q"
FCF_CONCEPTS = ("op_cash_flow", "capex", "revenue", "operating_income")


def _unresolvable(reason: str, deadline: date, **extra) -> tuple[str, dict]:
    # resolution_date = the date we stopped looking, so the dashboard never shows null.
    return "unresolvable", {"reason": reason, "resolution_date": str(deadline), "checked_through": str(deadline), **extra}


def first_visible_day(available, lo: date, hi: date) -> date | None:
    """Earliest day in (lo, hi] on which `available(day)` holds (it never turns false once true:
    a restatement replaces a value, it does not remove a quarter). Binary search over days."""
    if not available(hi):
        return None
    lo_d, hi_d = lo, hi
    while (hi_d - lo_d).days > 1:
        mid = lo_d + timedelta(days=(hi_d - lo_d).days // 2)
        if available(mid):
            hi_d = mid
        else:
            lo_d = mid
    return hi_d


def _missing(table: dict[str, list[Quarter]]) -> list[str]:
    return [c for c, qs in table.items() if not qs]


def _ttm_ends(table: dict[str, list[Quarter]]) -> list[date]:
    ends = common_ends(table)
    return [e for e in ends if all(ttm(table[c], e) for c in table)]


def _margins(table: dict[str, list[Quarter]], end: date) -> dict[str, float] | None:
    t = {c: ttm(table[c], end) for c in table}
    if any(v is None for v in t.values()) or t["revenue"].value <= 0:
        return None
    rev = t["revenue"].value
    return {"fcf_margin_ttm": (t["op_cash_flow"].value - t["capex"].value) / rev,
            "operating_margin": t["operating_income"].value / rev}


def resolve_fundamentals(call: AgentCall) -> tuple[str, dict]:
    _check(call, FUNDAMENTALS_Q)
    deadline = call.as_of + timedelta(days=FUNDAMENTALS_RESOLUTION_DAYS)
    base = quarter_table(call.company_id, FCF_CONCEPTS, call.as_of)
    if m := _missing(base):
        return _unresolvable(f"concept not available at as_of: {m}", deadline)
    ends0 = _ttm_ends(base)
    if not ends0:
        return _unresolvable("no latest quarter with four quarters of history", deadline)
    q0 = ends0[-1]

    later = quarter_table(call.company_id, FCF_CONCEPTS, deadline)
    nxt = [e for e in common_ends(later) if e > q0 and run_ending_at(later["revenue"], e, 1)]
    # next quarter must follow Q0 directly (a gap would compare non-adjacent quarters)
    nxt = [e for e in nxt if 80 <= (e - q0).days <= 110]
    if not nxt:
        return _unresolvable("next quarter not filed (or not derivable) by the deadline", deadline,
                             latest_quarter=str(q0))
    q1 = nxt[0]
    res = first_visible_day(
        lambda d: all(any(q.period_end == q1 for q in qs)
                      for qs in quarter_table(call.company_id, FCF_CONCEPTS, d).values()),
        call.as_of, deadline)

    table = quarter_table(call.company_id, FCF_CONCEPTS, res)  # the view on the resolution date
    m0, m1 = _margins(table, q0), _margins(table, q1)
    if m0 is None or m1 is None:
        return _unresolvable("margins not computable on the resolution date", res, latest_quarter=str(q0))
    better = {k: m1[k] > m0[k] for k in m0}
    outcome = "yes" if all(better.values()) else "no"
    accessions = sorted({a for c in table for e in (q0, q1) if (t := ttm(table[c], e)) for a in t.accessions})
    return outcome, {"rule": FUNDAMENTALS_Q, "resolution_date": str(res), "latest_quarter": str(q0),
                     "next_quarter": str(q1), "q0": m0, "q1": m1, "improved": better,
                     "decisive_metrics": [k for k, v in better.items() if not v] or list(better),
                     "basis": "values as known on the resolution date", "accessions": accessions}


def resolve_scenarios(call: AgentCall) -> tuple[str, dict]:
    _check(call, SCENARIOS_Q)
    deadline = call.as_of + timedelta(days=SCENARIOS_RESOLUTION_DAYS)
    base = quarter_table(call.company_id, ("revenue",), call.as_of)
    if _missing(base):
        return _unresolvable("revenue not available at as_of", deadline)
    ends0 = _ttm_ends(base)
    if not ends0:
        return _unresolvable("no latest quarter with four quarters of revenue", deadline)
    q0 = ends0[-1]

    later = quarter_table(call.company_id, ("revenue",), deadline)["revenue"]
    fwd = [q for q in later if q.period_end > q0][:4]  # `later` is sorted by period_end
    ok = len(fwd) == 4 and 80 <= (fwd[0].period_end - q0).days <= 110 and \
        run_ending_at(later, fwd[3].period_end, 4) is not None and \
        run_ending_at(later, fwd[3].period_end, 4)[0].period_end == fwd[0].period_end
    if not ok:
        return _unresolvable("fewer than four consecutive next quarters filed by the deadline", deadline,
                             latest_quarter=str(q0), quarters_found=len(fwd))
    ends = {q.period_end for q in fwd}
    res = first_visible_day(
        lambda d: ends <= {q.period_end for q in quarter_table(call.company_id, ("revenue",), d)["revenue"]},
        call.as_of, deadline)

    rev = quarter_table(call.company_id, ("revenue",), res)["revenue"]
    trailing = ttm(rev, q0)
    nxt = ttm(rev, fwd[3].period_end)
    if trailing is None or nxt is None or trailing.value <= 0:
        return _unresolvable("trailing revenue missing or not positive", res, latest_quarter=str(q0))
    growth = nxt.value / trailing.value - 1.0
    return bucket_for_growth(growth), {
        "rule": SCENARIOS_Q, "resolution_date": str(res), "latest_quarter": str(q0),
        "trailing_revenue": trailing.value, "next_4q_revenue": nxt.value, "revenue_growth": growth,
        "decisive_metrics": ["revenue_growth_yoy"], "basis": "values as known on the resolution date",
        "accessions": sorted(set(trailing.accessions) | set(nxt.accessions))}


def _check(call: AgentCall, qid: str) -> None:
    if call.claim.question_id != qid:
        raise ValueError(f"expected {qid}, got {call.claim.question_id}")
