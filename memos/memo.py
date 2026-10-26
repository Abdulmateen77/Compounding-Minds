"""Analyst memo drafting (README 11b.2). The LLM writes words; Python writes every number.

The drafter (an LLM call through the gateway, so through Mubit) writes four prose sections.
It refers to numbers only through placeholders, which Python fills from the metrics engine
and the stored calls:

    {{metric:<agent>.<name>}}       a metric value, e.g. {{metric:risk.interest_coverage}}
    {{call:<agent>.answer}}         an agent's answer
    {{call:<agent>.probability}}    an agent's probability
    {{verdict}} {{verdict.confidence}}

`check_prose` rejects the draft if, outside placeholders, it contains ANY digit, an unknown
placeholder, or buy/sell language. One repair retry, then the memo is rendered without
LLM prose (every Python-built section still appears). Research tool, not advice.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from agents.gateway import LLMGateway
from agents.runner import _extract_json
from schemas import AgentCall

log = logging.getLogger("memos")

MEMO_TAG = "ANALYST MEMO DRAFTER"
SECTIONS = (("summary", "Business outlook summary"), ("views", "Agent views and disagreements"),
            ("risks", "Risks and distress flags"), ("change", "What would change the view"))
DISCLAIMER = "Research tool, not financial advice."
_PLACEHOLDER = re.compile(r"\{\{([a-z_]+(?::[a-z_]+\.[a-z0-9_]+|\.[a-z_]+)?)\}\}")
_BANNED = re.compile(r"\b(buy|sell|short(?:ing)? the|price target|should invest|we recommend|undervalued stock)\b", re.I)

SYSTEM = f"""{MEMO_TAG}
You draft a short research memo from analyst calls that are already made. Write plain prose.
NEVER write a digit. Refer to any number only with a placeholder from the list you are given,
copied exactly, for example {{{{metric:risk.interest_coverage}}}} or {{{{call:risk.probability}}}}.
Do not give buy, sell or price advice. Do not name the company: use its anonymous id.
Reply with ONE JSON object:
{{"summary": "...", "views": "...", "risks": "...", "change": "..."}}
summary: the committee view in two or three sentences. views: where analysts agree and disagree.
risks: distress signals. change: which metrics or principles would change the view."""


@dataclass
class MemoInputs:
    company_id: str
    as_of: date
    metrics: dict[str, dict]            # agent -> get_metrics bundle
    calls: list[AgentCall]
    verdict: AgentCall | None = None

    def values(self) -> dict[str, str]:
        """Every placeholder this memo may use, mapped to its Python-formatted value."""
        out: dict[str, str] = {}
        for agent, bundle in self.metrics.items():
            for m in bundle["metrics"]:
                out[f"metric:{agent}.{m['name']}"] = format_value(m["value"], m["unit"])
        for c in self.calls:
            out[f"call:{c.agent}.answer"] = c.claim.answer
            out[f"call:{c.agent}.probability"] = f"{c.claim.probability:.0%}"
        if self.verdict:
            out["verdict"] = self.verdict.claim.answer
            out["verdict.confidence"] = f"{self.verdict.claim.probability:.0%}"
        return out


@dataclass
class Memo:
    markdown: str
    prose_ok: bool
    problems: list[str] = field(default_factory=list)


def format_value(value: float, unit: str) -> str:
    if unit == "ratio":
        return f"{value:.1%}"
    if unit == "x":
        return f"{value:.2f}x"
    if unit == "count":
        return f"{value:g}"
    return f"{value:g} {unit}".strip()


def check_prose(text: str, allowed: set[str]) -> list[str]:
    problems = [f"unknown placeholder {{{{{p}}}}}" for p in _PLACEHOLDER.findall(text) if p not in allowed]
    bare = _PLACEHOLDER.sub("", text)
    if hit := re.search(r".{0,20}\d.{0,20}", bare):
        problems.append(f"digit outside a placeholder: {hit.group(0)!r}")
    if "{{" in bare or "}}" in bare:
        problems.append("malformed placeholder")
    if m := _BANNED.search(bare):
        problems.append(f"advice language: {m.group(0)!r}")
    return problems


def fill(text: str, values: dict[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def build_messages(inp: MemoInputs) -> list[dict]:
    values = inp.values()
    lines = [f"- {{{{{k}}}}} = {v}" for k, v in values.items()]
    calls = [f"- {c.agent}: answered {{{{call:{c.agent}.answer}}}} at {{{{call:{c.agent}.probability}}}}, "
             f"principles {', '.join(c.principles_used) or 'none'}, evidence "
             + ", ".join(f"{{{{metric:{c.agent}.{e.metric}}}}}" for e in c.evidence) for c in inp.calls]
    user = (f"Company: {inp.company_id} (latest reported quarter)\n"
            + ("Committee verdict: {{verdict}} at {{verdict.confidence}}\n" if inp.verdict else "")
            + "ANALYST CALLS\n" + "\n".join(calls)
            + "\nPLACEHOLDERS YOU MAY USE (values shown for context only; never write them out)\n" + "\n".join(lines))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _parse(raw: str, allowed: set[str]) -> dict[str, str]:
    d = _extract_json(raw)
    out, problems = {}, []
    for key, _ in SECTIONS:
        text = str(d.get(key, "")).strip()
        if not text:
            problems.append(f"missing section {key!r}")
        problems += [f"{key}: {p}" for p in check_prose(text, allowed)]
        out[key] = text
    if problems:
        raise ValueError("; ".join(problems))
    return out


def draft_prose(inp: MemoInputs, gateway: LLMGateway) -> tuple[dict[str, str] | None, list[str]]:
    allowed = set(inp.values())
    messages = build_messages(inp)
    problems: list[str] = []
    for attempt in range(2):
        raw = gateway.complete("memo", messages, purpose="memo", session_id=f"memo:{inp.company_id}:{inp.as_of}")
        try:
            return _parse(raw, allowed), problems
        except (ValueError, TypeError) as err:
            problems.append(str(err))
            log.warning("memo draft rejected (attempt %d): %s", attempt + 1, err)
            messages = messages + [{"role": "assistant", "content": raw},
                                   {"role": "user", "content": f"Rejected: {err}. Fix it. No digits outside placeholders."}]
    return None, problems


def render(inp: MemoInputs, prose: dict[str, str] | None) -> str:
    values = inp.values()
    by_agent = {c.agent: c for c in inp.calls}
    out = [f"# Research memo: {inp.company_id}, as of {inp.as_of.isoformat()}", ""]
    if inp.verdict:
        out += [f"**Committee verdict:** {values['verdict']} ({values['verdict.confidence']} confidence)", ""]
    for key, title in SECTIONS:
        out += [f"## {title}", ""]
        if key == "views":
            for c in inp.calls:
                # Tool-sourced evidence (e.g. a past quarter) has no placeholder; its value is still Python's.
                ev = ", ".join(f"{e.metric} {values.get(f'metric:{c.agent}.{e.metric}', f'{e.value:g}')}" for e in c.evidence)
                out.append(f"- **{c.agent}**: {c.claim.answer} at {values[f'call:{c.agent}.probability']} "
                           f"(principles: {', '.join(c.principles_used) or 'none'}; evidence: {ev})")
            out.append("")
        if key == "risks" and "risk" in by_agent:
            r = by_agent["risk"]
            out += [f"Risk analyst: distress event in 12 months **{r.claim.answer}** at {values['call:risk.probability']}.", ""]
        out += [fill(prose[key], values) if prose else "_Drafted prose unavailable: it failed the number check._", ""]
        if key == "summary":
            out += ["## Key metrics", "", "| agent | metric | value | source accessions |", "|---|---|---|---|"]
            for agent, bundle in inp.metrics.items():
                for m in bundle["metrics"]:
                    out.append(f"| {agent} | {m['name']} | {format_value(m['value'], m['unit'])} | {', '.join(m['inputs'])} |")
            out.append("")
    accessions = sorted({a for b in inp.metrics.values() for m in b["metrics"] for a in m["inputs"]})
    out += ["## Source accessions", "", *[f"- {a}" for a in accessions], "", "---", "", f"*{DISCLAIMER}*", ""]
    return "\n".join(out)


def write_memo(inp: MemoInputs, gateway: LLMGateway) -> Memo:
    prose, problems = draft_prose(inp, gateway)
    return Memo(render(inp, prose), prose is not None, problems)
