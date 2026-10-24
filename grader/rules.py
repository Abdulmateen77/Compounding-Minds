"""Real outcome rules, routed by question_id (README 8.2). Pass `rules_outcome` as outcome_fn.

Only the Risk rule is real so far; other questions still use the stub until their rules land.
"""
from __future__ import annotations

from schemas import AgentCall

from .grade import stub_outcome
from .risk import QUESTION_ID as RISK_Q, resolve_distress
from .sapling import SaplingClient

_sapling: SaplingClient | None = None


def set_sapling(client: SaplingClient | None) -> None:
    """e.g. set_sapling(SaplingClient(replay_only=True)) for the demo."""
    global _sapling
    _sapling = client


def rules_outcome(call: AgentCall) -> tuple[str, dict | None]:
    if call.claim.question_id == RISK_Q:
        return resolve_distress(call, sapling=_sapling)
    return stub_outcome(call)  # TODO(owner A): fundamentals and scenarios rules
