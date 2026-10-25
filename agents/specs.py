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
    # principles/<file>.md. Defaults to the investor. Moat gets its own file so the
    # Fundamentals prompt (also Buffett) never changes: it is that agent's Mubit task key.
    principles: str = ""

    @property
    def principles_file(self) -> str:
        return self.principles or self.investor


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
            "Start from the bucket revenue_growth_mean_5y falls in (dalio.04: mean reversion is the default). Move to "
            "another bucket only if revenue_growth_yoy and the macro metrics both point to it.",
        )),
    # Stretch agents (README 7.1). Same runner, same AgentCall shape.
    "valuation": AgentSpec(
        "valuation", "graham", "implied_growth_above_delivered",
        "Is the revenue growth implied by the current valuation (reverse DCF) ABOVE the revenue growth the business will actually deliver over the next 12 months?",
        "binary", ("yes", "no"), "12_months"),
    "moat": AgentSpec(
        "moat", "buffett", "gross_margin_holds_2pts",
        "Will gross margin stay within plus or minus 2 percentage points of the latest quarter's level in each of the next four reported quarters?",
        "binary", ("yes", "no"), "4_quarters", principles="buffett_moat"),
}

MVP_AGENTS: tuple[str, ...] = ("fundamentals", "risk", "scenarios")
STRETCH_AGENTS: tuple[str, ...] = ("valuation", "moat")
