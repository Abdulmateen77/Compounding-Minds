"""Cross-examination round (README 7.3 stretch, ARCHITECTURE 7). One round, optional.

Runs AFTER every agent has committed and its call is stored. Each agent sees its peers'
answers and cited evidence, may challenge them, and may revise its own CONFIDENCE only:
* the answer never changes, and the stored original call is never touched
* the revision is capped (MAX_SHIFT) so one round cannot flip a calibrated view
* a reply that fails to parse keeps the original probability

The synthesizer can then use the revised copies. Every revision is returned for the record.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

from schemas import AgentCall

from .gateway import LLMGateway
from .masking import mask_dates
from .runner import _extract_json
from .specs import SPECS

log = logging.getLogger("agents.cross_exam")

CROSS_TAG = "CROSS-EXAMINATION"
MAX_SHIFT = 0.15


@dataclass(frozen=True)
class Revision:
    agent: str
    call_id: str
    original_probability: float
    revised_probability: float
    challenge: str
    parsed: bool


def build_cross_messages(call: AgentCall, peers: list[AgentCall], as_of: date) -> list[dict]:
    spec = SPECS[call.agent]
    # Stable system prompt per agent (Mubit groups calls into a task by it).
    system = (
        f"{CROSS_TAG}\nYou are the {spec.agent} analyst following {spec.investor.title()}'s principles. "
        "Your call is already committed. Read the other analysts' calls, challenge any evidence that "
        "conflicts with yours, and say whether your probability should move. You may NOT change your answer.\n"
        'Reply with ONE JSON object: {"probability": <0..1, your revised probability that your answer is right>, '
        '"challenge": "<one or two sentences naming the peer and the metric>"}. Research, not advice.'
    )
    mine = "; ".join(f"{e.metric}={e.value}" for e in call.evidence)
    rows = []
    for p in peers:
        ev = "; ".join(f"{e.metric}={e.value}" for e in p.evidence)
        why = " ".join(mask_dates(r, as_of) for r in p.reasoning)
        rows.append(f"- {p.agent}: {p.claim.answer} at {p.claim.probability:.2f}. Evidence: {ev}. Reasons: {why}")
    user = (f"YOUR CALL ({spec.question_id}): {call.claim.answer} at {call.claim.probability:.2f}. Evidence: {mine}\n"
            f"PEER CALLS (same company, same quarter)\n" + "\n".join(rows))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _clamp(original: float, revised: float) -> float:
    revised = min(1.0, max(0.0, revised))
    return round(min(original + MAX_SHIFT, max(original - MAX_SHIFT, revised)), 4)


def cross_examine(calls: list[AgentCall], gateway: LLMGateway) -> tuple[list[AgentCall], list[Revision]]:
    """Return revised COPIES of `calls` (for the synthesizer) and the revision record."""
    if len(calls) < 2:
        return list(calls), []
    as_of = calls[0].as_of
    revised, record = [], []
    for call in calls:
        peers = [p for p in calls if p.call_id != call.call_id]
        prob, challenge, ok = call.claim.probability, "", False
        try:
            raw = gateway.complete(call.agent, build_cross_messages(call, peers, as_of),
                                   purpose="cross_exam", session_id=f"cross:{call.call_id}")
            d = _extract_json(raw)
            prob = _clamp(call.claim.probability, float(d["probability"]))
            challenge, ok = str(d.get("challenge", "")).strip()[:400], True
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as err:
            log.warning("cross-exam reply for %s unusable, keeping original: %s", call.agent, err)
        record.append(Revision(call.agent, call.call_id, call.claim.probability, prob, challenge, ok))
        revised.append(call.model_copy(update={
            "claim": call.claim.model_copy(update={"probability": prob}), "confidence": prob}))
    return revised, record
