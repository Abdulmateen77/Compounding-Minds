"""Pick the misses and turn them into Correction objects (README 6.3, 8.3). Pure Python.

Selection: only calls with correct is False (unresolvable and correct calls never produce one).
At most `cap` per agent per quarter, highest confidence first (ties: call_id, so it is
deterministic). The quarter is the one in which the call was graded (resolution_date), which is
the batch the replay loop hands over after each quarter.

error_type, first match wins:
  overconfident  confidence >= config.OVERCONFIDENT_AT
  missed_regime  a bucket call that missed by two steps (bull vs bear), or the snapshot shows
                 gdp_growth_yoy below config.REGIME_GDP_GROWTH_BELOW
  ignored_metric the metrics that decided the outcome (grade evidence `decisive_metrics`) appear
                 nowhere in the call's evidence or reasoning
  wrong_signal   otherwise: the agent used the right metrics and read them wrongly

`lesson`: a short template. With a `gateway`, the reflection LLM call in agents/reflection.py
(routed through Mubit) writes the lesson and principle_refs instead; error_type stays the
rule-based one above so it is reproducible. If reflection drops the call, the template is used,
so a miss is never silently lost.

Interface matches grader/replay.py: make_corrections(items, gateway) where items are
agents.reflection.GradedCall(call, grade, metrics) or plain (call, grade) tuples.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from typing import Any

from schemas import AgentCall, Correction, Grade
from schemas.models import ErrorType

from .config import (BUCKET_ORDER, MAX_CORRECTIONS_PER_AGENT_PER_QUARTER, OVERCONFIDENT_AT,
                     REGIME_GDP_GROWTH_BELOW)

_NS = uuid.UUID("6f1c1c52-5a0e-4c35-9b0f-2d1a5d3f0c11")


def quarter_of(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _parts(item: Any) -> tuple[AgentCall, Grade, Any]:
    if isinstance(item, tuple):
        return item[0], item[1], None
    return item.call, item.grade, getattr(item, "metrics", None)


def _metric(metrics: Any, name: str) -> float | None:
    """metrics is {name: value|{value}} or the agents bundle {"metrics": [{name, value, ...}]}."""
    if isinstance(metrics, dict) and isinstance(metrics.get("metrics"), list):
        return next((m.get("value") for m in metrics["metrics"] if m.get("name") == name), None)
    v = (metrics or {}).get(name) if isinstance(metrics, dict) else None
    return v.get("value") if isinstance(v, dict) else v


def classify_error(call: AgentCall, grade: Grade, metrics: Any = None) -> ErrorType:
    if call.confidence >= OVERCONFIDENT_AT:
        return "overconfident"
    if call.claim.type == "bucket" and call.claim.answer in BUCKET_ORDER and grade.outcome in BUCKET_ORDER \
            and abs(BUCKET_ORDER.index(call.claim.answer) - BUCKET_ORDER.index(grade.outcome)) == 2:
        return "missed_regime"
    gdp = _metric(metrics, "gdp_growth_yoy")
    if isinstance(gdp, (int, float)) and gdp < REGIME_GDP_GROWTH_BELOW:
        return "missed_regime"
    decisive = {m for ev in grade.evidence for m in ev.get("decisive_metrics", [])}
    cited = " ".join([e.metric for e in call.evidence] + call.reasoning)
    if decisive and not any(m in cited for m in decisive):
        return "ignored_metric"
    return "wrong_signal"


def default_lesson(call: AgentCall, grade: Grade, error_type: str) -> str:
    decisive = sorted({m for ev in grade.evidence for m in ev.get("decisive_metrics", [])})
    return (f"{call.agent} said {call.claim.answer} on {call.claim.question_id} at confidence "
            f"{call.confidence:.2f}; the filings showed {grade.outcome} ({error_type}). "
            f"Metrics that decided it: {', '.join(decisive) or 'n/a'}.")


def select_misses(items: list[Any], cap: int = MAX_CORRECTIONS_PER_AGENT_PER_QUARTER) -> list[Any]:
    """Wrong calls only; per (agent, quarter graded) the `cap` most confident (ties by call_id)."""
    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for it in items:
        call, g, _ = _parts(it)
        if g.correct is False:  # unresolvable (None) and correct calls never qualify
            groups[(call.agent, quarter_of(g.resolution_date or call.as_of))].append(it)
    out: list[Any] = []
    for key in sorted(groups):
        out.extend(sorted(groups[key], key=lambda it: (-_parts(it)[0].confidence, _parts(it)[0].call_id))[:cap])
    return out


def make_corrections(items: list[Any], gateway: Any = None,
                     cap: int = MAX_CORRECTIONS_PER_AGENT_PER_QUARTER,
                     metrics: dict[str, Any] | None = None, lesson_fn: Any = None) -> list[Correction]:
    """`metrics` (call_id -> bundle) is for plain (call, grade) items. `lesson_fn(call, grade,
    error_type) -> str` overrides the lesson (grader/replay.py uses it); else `gateway` (reflection
    LLM) if given; else the template."""
    out: list[Correction] = []
    for it in select_misses(items, cap):
        call, g, m = _parts(it)
        metrics_ = m if m is not None else (metrics or {}).get(call.call_id)
        et = classify_error(call, g, metrics_)
        lesson, refs = default_lesson(call, g, et), list(call.principles_used)
        if lesson_fn is not None:
            lesson = lesson_fn(call, g, et)
        elif gateway is not None and not isinstance(it, tuple):
            from agents.reflection import reflect  # lazy: agents imports grader.config
            llm = reflect(it, gateway)
            if llm is not None:
                lesson, refs = llm.lesson, llm.principle_refs
        out.append(Correction(
            correction_id=str(uuid.uuid5(_NS, call.call_id)), call_id=call.call_id, agent=call.agent,
            company_id=call.company_id, as_of=call.as_of,
            predicted={"answer": call.claim.answer, "probability": call.claim.probability},
            actual={"outcome": g.outcome, "evidence": g.evidence},
            error_type=et, lesson=lesson, principle_refs=refs,
            inputs_snapshot={"metrics": (metrics_ or {}).get("metrics", metrics_ or {}) if isinstance(metrics_, dict) else {},
                             "reasoning": call.reasoning,
                             "evidence": [e.model_dump(mode="json") for e in call.evidence]}))
    return out
