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
        "bucket", ("bear", "base", "bull"), "4_quarters"),
}
