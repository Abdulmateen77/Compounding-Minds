"""Shared agent runner (README 7). Judge only: numbers come in, one AgentCall comes out.

1. load principles/<investor>.md  2. receive anon company_id + precomputed metrics
3. (MCP tool use, max ~5, comes later)  4. return one AgentCall; invalid JSON gets one
repair retry, then the call is dropped and logged.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from schemas import AgentCall

from .gateway import LLMGateway, ModelUpdater
from .masking import mask_dates
from .specs import SPECS

log = logging.getLogger("agents.runner")
PRINCIPLES_DIR = Path(__file__).resolve().parent.parent / "principles"

OUTPUT_SHAPE = """Reply with ONE JSON object and nothing else:
{
  "claim": {"type": "<binary|bucket>", "question_id": "<given>", "answer": "<one of the allowed answers>", "probability": <0..1, probability your answer is correct>},
  "confidence": <0..1, same as probability>,
  "reasoning": ["max 5 short bullets, each citing a metric name"],
  "evidence": [{"metric": "<name from the metrics>", "value": <exact value given>}],
  "principles_used": ["<ids from the principles list>"]
}
Use only the metrics provided. Do not invent numbers. Time is relative: Q0 is the latest
reported quarter, Q-1 the one before. This is research, not investment advice."""


def load_principles(investor: str) -> str:
    return (PRINCIPLES_DIR / f"{investor}.md").read_text()


def build_messages(agent: str, company_id: str, as_of: date, metrics: dict, lessons: list[str]) -> list[dict]:
    spec = SPECS[agent]
    # Prompts carry only the anon id and metrics: no names, tickers or calendar dates.
    # Names, units and lessons are masked; numeric values are passed through untouched.
    mask = lambda s: mask_dates(str(s), as_of)  # noqa: E731
    lines = [f"- {mask(m['name'])} = {m['value']} {mask(m['unit'])}" for m in metrics["metrics"]]
    memory = "\n".join(f"- {mask(l)}" for l in lessons) or "- (none yet)"
    # The system prompt must stay identical across calls: Mubit groups calls into one task
    # by their instructions, so anything that changes (lessons, company, metrics) goes in
    # the user message.
    system = (
        f"You are the {spec.agent} analyst following {spec.investor.title()}'s principles.\n\n"
        f"PRINCIPLES\n{load_principles(spec.investor)}\n\n{OUTPUT_SHAPE}"
    )
    user = (
        f"LESSONS FROM PAST MISTAKES (apply them)\n{memory}\n\n"
        f"Company: {company_id}\nQuestion ({spec.question_id}): {spec.question}\n"
        f"Allowed answers: {', '.join(spec.answers)}\nHorizon: {spec.horizon}\n"
        + "".join(f"RULE: {r}\n" for r in spec.extra_rules)
        + f"as_of: Q0 (latest reported quarter; calendar dates are hidden)\nMETRICS\n" + "\n".join(lines)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    return json.loads(m.group(0))


def _check_evidence(call: AgentCall, metrics: dict) -> None:
    """Evidence must match what the metrics engine returned, else the call is rejected."""
    known = {m["name"]: m["value"] for m in metrics["metrics"]}
    for e in call.evidence:
        if e.metric not in known:
            raise ValueError(f"evidence mismatch: {e.metric!r} is not a metric name. "
                             f"Use exactly one of: {', '.join(sorted(known))}")
        if abs(known[e.metric] - e.value) > 1e-9:
            raise ValueError(f"evidence mismatch: {e.metric!r} must have the exact value {known[e.metric]}")


def _parse(raw: str, agent: str, company_id: str, as_of: date, run_id: str, metrics: dict, model: str) -> AgentCall:
    spec = SPECS[agent]
    d = _extract_json(raw)
    d.setdefault("claim", {})
    d["claim"].update(type=spec.claim_type, question_id=spec.question_id)  # fixed by us, not the model
    if d["claim"].get("answer") not in spec.answers:
        raise ValueError(f"answer must be one of {spec.answers}")
    # The model never sees the real date, so we stamp it on the evidence ourselves.
    d["evidence"] = [{**e, "as_of": as_of.isoformat()} if isinstance(e, dict) else e for e in d.get("evidence", [])]
    d.update(call_id=str(uuid.uuid4()), run_id=run_id, agent=agent, company_id=company_id,
             as_of=as_of.isoformat(), horizon=spec.horizon, tool_calls=0, model=model)
    call = AgentCall.model_validate(d)
    _check_evidence(call, metrics)
    return call


def run_agent(agent: str, company_id: str, as_of: date, metrics: dict, gateway: LLMGateway,
              updater: ModelUpdater, run_id: str | None = None, lessons: list[str] | None = None) -> AgentCall | None:
    run_id = run_id or str(uuid.uuid4())
    model = updater.get_model_version(agent)
    lessons = lessons if lessons is not None else getattr(updater, "lessons", lambda a: [])(agent)
    messages = build_messages(agent, company_id, as_of, metrics, lessons)
    # Mubit session: one per agent, company and quarter (metadata only, the model never sees it).
    session = f"{agent}:{company_id}:{as_of.isoformat()}"
    raw = gateway.complete(agent, messages, session_id=session)
    try:
        return _parse(raw, agent, company_id, as_of, run_id, metrics, model)
    except (ValueError, ValidationError, json.JSONDecodeError) as err:
        problem = str(err)
        log.warning("repair retry for %s %s %s: %s", agent, company_id, as_of, problem)
    repair = messages + [{"role": "assistant", "content": raw},
                         {"role": "user", "content": f"That reply was invalid ({problem}). Return only the corrected JSON object."}]
    try:
        return _parse(gateway.complete(agent, repair, session_id=session), agent, company_id, as_of, run_id, metrics, model)
    except (ValueError, ValidationError, json.JSONDecodeError) as err2:
        log.error("DROPPED call %s %s %s: %s", agent, company_id, as_of, err2)
        return None
