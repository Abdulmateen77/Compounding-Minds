"""Shared agent runner (README 7). Judge only: numbers come in, one AgentCall comes out.

1. load principles/<investor>.md  2. receive anon company_id + precomputed metrics
3. optional read-only tool calls, at most 5 (agents/tools.py)  4. return one AgentCall;
invalid JSON gets one repair retry, then the call is dropped and logged.
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
from .tools import MAX_TOOL_CALLS, Toolbox, ToolError, format_rows

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

# Appended to the USER message only when tools are enabled, so the system prompt (Mubit's
# task key) and the no-tools prompts stay byte-for-byte the same.
TOOL_INSTRUCTIONS = """TOOLS (optional, at most {n} calls in total). To call one, reply with ONLY
{{"tool": "<name>", "args": {{...}}}}. The result arrives in the next message. You may cite a
tool value in evidence by its exact name. When you are done, reply with the final JSON answer.
{lines}"""


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
        f"PRINCIPLES\n{load_principles(spec.principles_file)}\n\n{OUTPUT_SHAPE}"
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


def _check_evidence(call: AgentCall, metrics: dict, extra: dict[str, float] | None = None) -> None:
    """Evidence must match what the metrics engine (or a tool) returned, else the call is rejected."""
    known = {m["name"]: m["value"] for m in metrics["metrics"]}
    known.update(extra or {})
    for e in call.evidence:
        if e.metric not in known:
            raise ValueError(f"evidence mismatch: {e.metric!r} is not a metric name. "
                             f"Use exactly one of: {', '.join(sorted(known))}")
        if abs(known[e.metric] - e.value) > 1e-9:
            raise ValueError(f"evidence mismatch: {e.metric!r} must have the exact value {known[e.metric]}")


def _parse(raw: str, agent: str, company_id: str, as_of: date, run_id: str, metrics: dict, model: str,
           tool_calls: int = 0, extra: dict[str, float] | None = None) -> AgentCall:
    spec = SPECS[agent]
    d = _extract_json(raw)
    d.setdefault("claim", {})
    d["claim"].update(type=spec.claim_type, question_id=spec.question_id)  # fixed by us, not the model
    if d["claim"].get("answer") not in spec.answers:
        raise ValueError(f"answer must be one of {spec.answers}")
    # The model never sees the real date, so we stamp it on the evidence ourselves.
    d["evidence"] = [{**e, "as_of": as_of.isoformat()} if isinstance(e, dict) else e for e in d.get("evidence", [])]
    d.update(call_id=str(uuid.uuid4()), run_id=run_id, agent=agent, company_id=company_id,
             as_of=as_of.isoformat(), horizon=spec.horizon, tool_calls=tool_calls, model=model)
    call = AgentCall.model_validate(d)
    _check_evidence(call, metrics, extra)
    return call


def _tool_request(raw: str) -> tuple[str, dict] | None:
    try:
        d = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    if isinstance(d, dict) and "tool" in d and "claim" not in d:
        return str(d["tool"]), d.get("args") if isinstance(d.get("args"), dict) else {}
    return None


def run_agent(agent: str, company_id: str, as_of: date, metrics: dict, gateway: LLMGateway,
              updater: ModelUpdater, run_id: str | None = None, lessons: list[str] | None = None,
              toolbox: Toolbox | None = None, max_tool_calls: int = MAX_TOOL_CALLS,
              record: bool = True) -> AgentCall | None:
    """`record=False`: Mubit answers but keeps nothing (held-out eval, controls), so it can't train on the call."""
    run_id = run_id or str(uuid.uuid4())
    kw = {} if record else {"record": False}   # only sent when False, so gateways without the option are untouched
    model = updater.get_model_version(agent)
    lessons = lessons if lessons is not None else getattr(updater, "lessons", lambda a: [])(agent)
    messages = build_messages(agent, company_id, as_of, metrics, lessons)
    if toolbox is not None:
        lines = "\n".join(f"- {t}" for t in toolbox.specs())
        messages[1] = {**messages[1], "content": messages[1]["content"] + "\n\n"
                       + TOOL_INSTRUCTIONS.format(n=max_tool_calls, lines=lines)}
    # Mubit session: one per agent, company and quarter (metadata only, the model never sees it).
    session = f"{agent}:{company_id}:{as_of.isoformat()}"
    convo = list(messages)
    extra: dict[str, float] = {}
    n_tools = 0
    raw = gateway.complete(agent, list(convo), session_id=session, **kw)
    while toolbox is not None and (req := _tool_request(raw)) is not None:
        convo.append({"role": "assistant", "content": raw})
        if n_tools >= max_tool_calls:
            convo.append({"role": "user", "content": "Tool limit reached. Reply now with the final JSON answer."})
            raw = gateway.complete(agent, list(convo), session_id=session, **kw)
            break
        name, args = req
        n_tools += 1
        try:
            rows = toolbox.call(name, args, company_id, agent, as_of)
            extra.update({r["name"]: r["value"] for r in rows if "name" in r})
            result = mask_dates(format_rows(name, rows), as_of)
        except (ToolError, ValueError, TypeError, KeyError) as err:
            result = f"TOOL ERROR {name}: {err}"
        convo.append({"role": "user", "content": result})
        raw = gateway.complete(agent, list(convo), session_id=session, **kw)
    try:
        return _parse(raw, agent, company_id, as_of, run_id, metrics, model, n_tools, extra)
    except (ValueError, ValidationError, json.JSONDecodeError) as err:
        problem = str(err)
        log.warning("repair retry for %s %s %s: %s", agent, company_id, as_of, problem)
    repair = convo + [{"role": "assistant", "content": raw},
                      {"role": "user", "content": f"That reply was invalid ({problem}). Return only the corrected JSON object."}]
    try:
        return _parse(gateway.complete(agent, repair, session_id=session, **kw), agent, company_id, as_of, run_id,
                      metrics, model, n_tools, extra)
    except (ValueError, ValidationError, json.JSONDecodeError) as err2:
        log.error("DROPPED call %s %s %s: %s", agent, company_id, as_of, err2)
        return None
