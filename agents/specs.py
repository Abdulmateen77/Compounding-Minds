"""Per-agent spec: investor, question, answer type, horizon (README 7.1). MVP agents first."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    agent: str
    investor: str
    question_id: str
    question: str
    claim_type: str          # binary | bucket
    answers: tuple[str, ...]
    horizon: str
    # Extra per-agent rules, appended to the USER message. Never the system prompt: Mubit
    # groups calls into a task by system prompt, so editing that would split the task.
    extra_rules: tuple[str, ...] = ()


SPECS: dict[str, AgentSpec] = {
    "fundamentals": AgentSpec(
        "fundamentals", "buffett", "fcf_margin_improves_next_q",
        "Will free cash flow margin AND operating margin both be higher in the next reported quarter than in the latest reported quarter?",
        "binary", ("yes", "no"), "next_quarter"),
    "risk": AgentSpec(
        "risk", "munger", "distress_event_12m",
        "In the next 12 months, will there be an auditor change, a dividend cut of at least 25 percent, or going-concern language?",
        "binary", ("yes", "no"), "12_months"),
    "scenarios": AgentSpec(
        "scenarios", "dalio", "revenue_bucket_next_4q",
        "Will revenue over the next four quarters, versus the trailing four, land in bear (<0% growth), base (0-10%) or bull (>10%)?",
        "bucket", ("bear", "base", "bull"), "4_quarters",
        extra_rules=(
            "Copy every metric name in `evidence` exactly as it is written in METRICS, prefix included "
            "(write `revenue_macro_beta`, never `macro_beta`). Do not shorten, rename or reword metric names.",
        )),
}
