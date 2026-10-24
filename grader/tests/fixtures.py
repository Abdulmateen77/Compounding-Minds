"""Offline fixtures: a synthetic company ("anon_001") with fake quarterly filings, fed to the
in-memory store backend. Nothing here touches the network or a real filing.

Calendar-year filer. 10-Qs are filed ~40 days after quarter end, the 10-K ~60 days after year end.
Income-statement items are tagged as discrete 3-month facts; cash-flow items as year-to-date
facts (3M, 6M, 9M, FY), exactly as filings report them, so the discrete-quarter derivation
(Q2 = 6M - 3M, Q4 = FY - 9M) is exercised.
"""
from __future__ import annotations

from datetime import date, timedelta

from schemas import AgentCall, Claim

CID = "anon_001"
Q_ENDS = [date(y, m, d) for y in range(2017, 2022) for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))]


def filed_for(end: date) -> date:
    return end + timedelta(days=60 if end.month == 12 else 40)


def _row(concept, value, start, end, filed, acc, form="10-Q", unit="USD"):
    return dict(company_id=CID, concept=concept, value=float(value), unit=unit, period_start=start,
                period_end=end, fiscal_period=None, form=form, accession=acc, filed_date=filed)


def income_rows(concept, by_end: dict[date, float]) -> list[dict]:
    """Discrete 3-month facts. (Q4 is filed with the 10-K; we also give it as a 3M fact.)"""
    out = []
    for end, v in by_end.items():
        start = date(end.year, end.month - 2, 1)
        out.append(_row(concept, v, start, end, filed_for(end), f"acc-{end:%Y%m%d}",
                        "10-K" if end.month == 12 else "10-Q"))
    return out


def cashflow_rows(concept, by_end: dict[date, float]) -> list[dict]:
    """Year-to-date facts from discrete quarterly values."""
    out = []
    for year in sorted({e.year for e in by_end}):
        ends = [e for e in sorted(by_end) if e.year == year]
        run = 0.0
        for e in ends:
            run += by_end[e]
            out.append(_row(concept, run, date(year, 1, 1), e, filed_for(e), f"acc-{e:%Y%m%d}",
                            "10-K" if e.month == 12 else "10-Q"))
    return out


def company(revenue, op_income, ocf, capex, ends=None) -> list[dict]:
    """Each argument: list of discrete quarterly values aligned with `ends` (default Q_ENDS)."""
    ends = ends or Q_ENDS[: len(revenue)]
    z = lambda xs: dict(zip(ends, xs))
    return (income_rows("revenue", z(revenue)) + income_rows("operating_income", z(op_income))
            + cashflow_rows("op_cash_flow", z(ocf)) + cashflow_rows("capex", z(capex)))


def restate(rows: list[dict], concept: str, end: date, new_value: float, filed: date, acc: str) -> list[dict]:
    """A later filing restating a discrete 3M income fact: a NEW row, the old one stays."""
    old = next(r for r in rows if r["concept"] == concept and r["period_end"] == end and r["period_start"].month == end.month - 2)
    return rows + [{**old, "value": float(new_value), "filed_date": filed, "accession": acc, "form": "10-K/A"}]


def call(question_id: str, answer: str, prob: float = 0.7, as_of: date = date(2019, 6, 30), agent="fundamentals",
         claim_type="binary", call_id="c1", evidence=(), reasoning=("x",)) -> AgentCall:
    return AgentCall(call_id=call_id, run_id="r1", agent=agent, company_id=CID, as_of=as_of,
                     horizon="12_months" if agent in ("risk", "scenarios") else "next_quarter",
                     claim=Claim(type=claim_type, question_id=question_id, answer=answer, probability=prob),
                     confidence=prob, reasoning=list(reasoning), evidence=list(evidence), tool_calls=0, model="m")
