"""Outcome rules routed by question_id (README 8.2). Pass `rules_outcome` as outcome_fn.

Real: fcf_margin_improves_next_q, revenue_bucket_next_4q, distress_event_12m.
STUBS (marked `"stub": True` in the grade evidence, not in the MVP): implied_growth_above_delivered,
gross_margin_holds_2pts, committee_verdict. They return a deterministic fake outcome.
"""
from __future__ import annotations

from schemas import AgentCall

from .grade import stub_outcome
from .resolvers import FUNDAMENTALS_Q, SCENARIOS_Q, resolve_fundamentals, resolve_scenarios
from .risk import QUESTION_ID as RISK_Q, resolve_distress
from .sapling import SaplingClient

STUB_QUESTIONS = ("implied_growth_above_delivered", "gross_margin_holds_2pts", "committee_verdict")

_sapling: SaplingClient | None = None


def set_sapling(client: SaplingClient | None) -> None:
    """e.g. set_sapling(SaplingClient(replay_only=True)) for the demo."""
    global _sapling
    _sapling = client


def rules_outcome(call: AgentCall) -> tuple[str, dict | None]:
    q = call.claim.question_id
    if q == RISK_Q:
        return resolve_distress(call, sapling=_sapling)
    if q == FUNDAMENTALS_Q:
        return resolve_fundamentals(call)
    if q == SCENARIOS_Q:
        return resolve_scenarios(call)
    if q in STUB_QUESTIONS:
        return stub_outcome(call)
    raise ValueError(f"unknown question_id {q!r}")
