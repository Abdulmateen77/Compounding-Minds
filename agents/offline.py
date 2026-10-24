"""OFFLINE DEMO PIECES ONLY. Lets the correction loop run end to end without Mubit or a real LLM.

* `scripted_llm`: a rule-based stand-in for the LLM. As the analyst it follows the
  lessons in its prompt (so a correction visibly changes behaviour). As the reflection
  reviewer it writes a capex lesson.
* `demo_reality`: a stub "what the filings said" rule over the STUB metrics. It is not
  real data and not Person A's grader; swap in `grader.grade` with real rules later.

Never present output from this module as real results.
"""
from __future__ import annotations

import json
import re
from datetime import date

from grader.grade import stub_outcome
from schemas import AgentCall
from store.stubs import get_metrics_stub

from .reflection import REFLECTION_TAG
from .specs import SPECS
from .synthesizer import SYNTH_TAG

CAPEX_LIMIT = 0.05  # stub rule: FCF only improves when capex_to_revenue is below this
_METRIC_LINE = re.compile(r"^- (\w+) = (-?[\d.eE+-]+) ", re.M)
_CAPEX_LESSON = re.compile(r"capex_to_revenue (?:is )?(?:above|at or above|>=?) ([\d.]+)")


def _metrics_from(text: str) -> dict[str, float]:
    return {name: float(v) for name, v in _METRIC_LINE.findall(text)}


def _analyst(agent: str, messages: list[dict]) -> str:
    system, user = messages[0]["content"], messages[1]["content"]
    m = _metrics_from(user)
    spec = SPECS[agent]
    if agent == "risk":
        return _risk(m, spec)
    if agent == "scenarios":
        return _scenarios(m, spec)
    if agent != "fundamentals":  # minimal generic answer for stretch agents
        name, value = next(iter(m.items()))
        return json.dumps({
            "claim": {"type": spec.claim_type, "question_id": spec.question_id, "answer": spec.answers[0], "probability": 0.55},
            "confidence": 0.55, "reasoning": [f"{name} is {value}"],
            "evidence": [{"metric": name, "value": value}], "principles_used": []})

    # Naive v0 behaviour: FCF margin rising -> say yes.
    answer, prob = ("yes", 0.8) if m["fcf_margin_qoq_change"] > 0 else ("no", 0.7)
    reasoning = [f"fcf_margin_qoq_change is {m['fcf_margin_qoq_change']:+.3f}, cash conversion improving"]
    evidence = [{"metric": "fcf_margin_qoq_change", "value": m["fcf_margin_qoq_change"]}]
    principles = ["buffett.01"]

    # Learned behaviour: apply any capex lesson found in LESSONS FROM PAST MISTAKES.
    memory = user.split("LESSONS FROM PAST MISTAKES", 1)[-1].split("Company:", 1)[0]
    hit = _CAPEX_LESSON.search(memory)
    if hit and answer == "yes" and m["capex_to_revenue"] >= float(hit.group(1)):
        answer, prob = "no", 0.7
        reasoning.append(f"capex_to_revenue is {m['capex_to_revenue']}, above the lesson's limit, so discount the FCF rise")
        evidence.append({"metric": "capex_to_revenue", "value": m["capex_to_revenue"]})
        principles.append("buffett.03")

    return json.dumps({
        "claim": {"type": "binary", "question_id": spec.question_id, "answer": answer, "probability": prob},
        "confidence": prob, "reasoning": reasoning, "evidence": evidence, "principles_used": principles})


def _answer(spec, answer: str, prob: float, reasons: list[str], cited: dict[str, float], principles: list[str]) -> str:
    return json.dumps({
        "claim": {"type": spec.claim_type, "question_id": spec.question_id, "answer": answer, "probability": prob},
        "confidence": prob, "reasoning": reasons,
        "evidence": [{"metric": k, "value": v} for k, v in cited.items()], "principles_used": principles})


def _risk(m: dict[str, float], spec) -> str:
    keys = ("interest_coverage", "going_concern_hits", "cash_runway_quarters")
    cited = {k: m[k] for k in keys}
    if m["going_concern_hits"] > 0:
        return _answer(spec, "yes", 0.85, ["going_concern_hits above zero is near-decisive"], cited, ["munger.05"])
    if m["interest_coverage"] < 2 and m["cash_runway_quarters"] < 8:
        return _answer(spec, "yes", 0.65, ["interest_coverage below 2 with a short cash_runway_quarters"], cited, ["munger.02", "munger.03"])
    return _answer(spec, "no", 0.8, ["interest_coverage comfortable, no going_concern_hits"], cited, ["munger.06"])


def _scenarios(m: dict[str, float], spec) -> str:
    g = 0.5 * m["revenue_growth_yoy"] + 0.5 * m["revenue_growth_mean_5y"]  # mean reversion (dalio.04)
    bucket = "bear" if g < 0 else "bull" if g > 0.10 else "base"
    prob = 0.6 if m["revenue_growth_std_5y"] < 0.05 else 0.45  # wider spread, less confidence (dalio.05)
    cited = {k: m[k] for k in ("revenue_growth_yoy", "revenue_growth_mean_5y", "revenue_growth_std_5y")}
    return _answer(spec, bucket, prob, [f"revenue_growth_yoy blended with revenue_growth_mean_5y points to {bucket}"],
                   cited, ["dalio.04", "dalio.05"])


def _synth_rationale(messages: list[dict]) -> str:
    rows = [l[2:] for l in messages[1]["content"].splitlines() if l.startswith("- ")]
    return json.dumps({"reasoning": [r.split(". Reasons:")[0] for r in rows][:5]})


def _reflection(messages: list[dict]) -> str:
    m = _metrics_from(messages[1]["content"])
    if "capex_to_revenue" in m:
        return json.dumps({
            "error_type": "ignored_metric",
            "lesson": (f"When capex_to_revenue is above {CAPEX_LIMIT}, discount an FCF margin rise: heavy "
                       f"reinvestment tends to absorb the cash next quarter (refines buffett.03)."),
            "principle_refs": ["buffett.03"],
        })
    name = next(iter(m))
    return json.dumps({"error_type": "overconfident",
                       "lesson": f"When {name} is the only signal, keep probability near 0.55.",
                       "principle_refs": []})


def scripted_llm(agent: str, messages: list[dict]) -> str:
    if messages[0]["content"].startswith(REFLECTION_TAG):
        return _reflection(messages)
    if messages[0]["content"].startswith(SYNTH_TAG):
        return _synth_rationale(messages)
    return _analyst(agent, messages)


def demo_reality(call: AgentCall) -> tuple[str, dict]:
    """STUB outcome. Fundamentals: FCF improves only if FCF is rising AND capex_to_revenue < CAPEX_LIMIT."""
    if call.agent != "fundamentals":
        return stub_outcome(call)
    bundle = get_metrics_stub(call.company_id, call.agent, date.fromisoformat(str(call.as_of)))
    m = {x["name"]: x["value"] for x in bundle["metrics"]}
    improved = m["fcf_margin_qoq_change"] > 0 and m["capex_to_revenue"] < CAPEX_LIMIT
    return ("yes" if improved else "no"), {"stub": True, "rule": f"fcf rising and capex_to_revenue < {CAPEX_LIMIT}"}
