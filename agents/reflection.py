"""Reflection: a wrong graded call becomes a Correction (README 6.3, 8.3).

A separate "reflection" LLM call (routed through the same gateway, so through Mubit)
reads the call, the metrics the agent saw and what actually happened, then writes one
reusable lesson. The lesson must cite a metric or a principle and must never name the
company or a calendar year, so it generalises instead of memorising.

Selection (which wrong calls get reflected on) follows README 8.3: only incorrect calls,
highest confidence first, capped per agent per quarter.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import get_args

from pydantic import ValidationError

from grader.config import MAX_CORRECTIONS_PER_AGENT_PER_QUARTER
from schemas import AgentCall, Correction, Grade
from schemas.models import ErrorType

from .gateway import LLMGateway
from .runner import _extract_json, load_principles
from .specs import SPECS

log = logging.getLogger("agents.reflection")

ERROR_TYPES: tuple[str, ...] = get_args(ErrorType)
REFLECTION_TAG = "REFLECTION REVIEW"
_PRINCIPLE_ID = re.compile(r"^([a-z]+\.\d{2})\s*\|", re.M)
_COMPANY_ID = re.compile(r"\banon_\d{3}\b")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")

REFLECTION_SHAPE = """Reply with ONE JSON object and nothing else:
{
  "error_type": "<overconfident | missed_regime | wrong_signal | ignored_metric>",
  "lesson": "<one reusable rule, 1-2 sentences, citing a metric name or principle id>",
  "principle_refs": ["<ids from the principles list that the lesson refines>"]
}
error_type meanings:
- overconfident: the reasoning was defensible but the probability was too high for the evidence
- missed_regime: a macro or regime shift made the usual pattern fail
- wrong_signal: the agent leaned on a metric that pointed the wrong way
- ignored_metric: a metric in the inputs warned against the call and was not used
Rules for the lesson: write it as a rule for future calls ("When X, then Y").
Name metrics exactly as given. Never mention a company id, company name, ticker or calendar year."""


@dataclass(frozen=True)
class GradedCall:
    """One graded call plus the metrics bundle the agent saw when it made it."""

    call: AgentCall
    grade: Grade
    metrics: dict


def principle_ids(investor: str) -> set[str]:
    return set(_PRINCIPLE_ID.findall(load_principles(investor)))


def build_reflection_messages(item: GradedCall) -> list[dict]:
    call, grade = item.call, item.grade
    spec = SPECS[call.agent]
    lines = [f"- {m['name']} = {m['value']} {m['unit']}" for m in item.metrics["metrics"]]
    system = (
        f"{REFLECTION_TAG}\nYou review mistakes made by the {spec.agent} analyst, which follows "
        f"{spec.investor.title()}'s principles. Diagnose why the call was wrong using only the inputs "
        f"the analyst had, then write one reusable rule that would have prevented it.\n\n"
        f"PRINCIPLES\n{load_principles(spec.principles_file)}\n\n{REFLECTION_SHAPE}"
    )
    # No company id and no as_of date: the lesson must generalise, not memorise.
    user = (
        f"Question ({spec.question_id}): {spec.question}\n"
        f"Analyst answered: {call.claim.answer} with probability {call.claim.probability}\n"
        f"Analyst reasoning:\n" + "\n".join(f"- {r}" for r in call.reasoning) + "\n"
        f"Principles the analyst cited: {', '.join(call.principles_used) or '(none)'}\n"
        f"METRICS THE ANALYST SAW\n" + "\n".join(lines) + "\n"
        f"ACTUAL OUTCOME (from later filings): {grade.outcome}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_reflection(raw: str, item: GradedCall, known_principles: set[str]) -> Correction:
    d = _extract_json(raw)
    error_type = d.get("error_type")
    if error_type not in ERROR_TYPES:
        raise ValueError(f"error_type must be one of {ERROR_TYPES}")
    lesson = str(d.get("lesson", "")).strip()
    if not 20 <= len(lesson) <= 500:
        raise ValueError("lesson must be 20-500 characters")
    if _COMPANY_ID.search(lesson) or _YEAR.search(lesson):
        raise ValueError("lesson must not mention a company id or a calendar year")
    refs = list(d.get("principle_refs") or [])
    unknown = [r for r in refs if r not in known_principles]
    if unknown:
        raise ValueError(f"unknown principle ids {unknown}; use only {sorted(known_principles)}")
    metric_names = {m["name"] for m in item.metrics["metrics"]}
    if not any(name in lesson for name in metric_names | known_principles):
        raise ValueError("lesson must cite a metric name or principle id from the inputs")

    call, grade = item.call, item.grade
    return Correction(
        correction_id=str(uuid.uuid4()),
        call_id=call.call_id,
        agent=call.agent,
        company_id=call.company_id,
        as_of=call.as_of,
        predicted={"answer": call.claim.answer, "probability": call.claim.probability},
        actual={"outcome": grade.outcome, "evidence": grade.evidence},
        error_type=error_type,
        lesson=lesson,
        principle_refs=refs,
        inputs_snapshot={"metrics": item.metrics["metrics"], "reasoning": call.reasoning},
    )


def _with_request_id(c: Correction, gateway: LLMGateway) -> Correction:
    """Link the correction to the Mubit request that wrote its lesson (MubitGateway only)."""
    rid = getattr(gateway, "last_request_id", None)
    if rid:
        c.inputs_snapshot["mubit_request_id"] = rid
    return c


def reflect(item: GradedCall, gateway: LLMGateway) -> Correction | None:
    """One reflection call, one repair retry, then drop and log (same policy as the runner)."""
    if item.grade.correct is not False:
        return None
    known = principle_ids(SPECS[item.call.agent].principles_file)
    messages = build_reflection_messages(item)
    session = f"reflection:{item.call.call_id}"
    raw = gateway.complete(item.call.agent, messages, purpose="reflection", session_id=session)
    try:
        return _with_request_id(_parse_reflection(raw, item, known), gateway)
    except (ValueError, ValidationError, json.JSONDecodeError) as err:
        problem = str(err)
        log.warning("reflection repair retry for call %s: %s", item.call.call_id, problem)
    repair = messages + [{"role": "assistant", "content": raw},
                         {"role": "user", "content": f"That reply was invalid ({problem}). Return only the corrected JSON object."}]
    try:
        fixed = gateway.complete(item.call.agent, repair, purpose="reflection", session_id=session)
        return _with_request_id(_parse_reflection(fixed, item, known), gateway)
    except (ValueError, ValidationError, json.JSONDecodeError) as err2:
        log.error("DROPPED reflection for call %s: %s", item.call.call_id, err2)
        return None


def select_for_reflection(items: list[GradedCall], cap: int = MAX_CORRECTIONS_PER_AGENT_PER_QUARTER) -> list[GradedCall]:
    """Wrong calls only, most confident first, at most `cap` per (agent, as_of)."""
    groups: dict[tuple[str, object], list[GradedCall]] = defaultdict(list)
    for it in items:
        if it.grade.correct is False:
            groups[(it.call.agent, it.call.as_of)].append(it)
    picked: list[GradedCall] = []
    for group in groups.values():
        group.sort(key=lambda it: it.call.confidence, reverse=True)
        picked.extend(group[:cap])
    return picked


def make_corrections(items: list[GradedCall], gateway: LLMGateway,
                     cap: int = MAX_CORRECTIONS_PER_AGENT_PER_QUARTER) -> list[Correction]:
    out = []
    for it in select_for_reflection(items, cap):
        c = reflect(it, gateway)
        if c is not None:
            out.append(c)
    return out
