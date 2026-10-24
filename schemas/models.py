"""Shared Pydantic models. Mirrors README sections 4.5 and 6.1-6.3.

Either owner may edit this file, but tell the other person: agents must emit
exactly the AgentCall shape or grading and Mubit updates break.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AgentName = Literal[
    "fundamentals", "valuation", "moat", "risk", "scenarios", "synthesizer"
]
Horizon = Literal["next_quarter", "4_quarters", "12_months"]
ClaimType = Literal["binary", "bucket", "numeric_band"]
ErrorType = Literal["overconfident", "missed_regime", "wrong_signal", "ignored_metric"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- store rows (4.3 / 4.5) -------------------------------------------------

class Fact(_Strict):
    company_id: str
    concept: str
    value: float
    unit: str
    period_start: date | None = None
    period_end: date
    fiscal_period: str | None = None
    form: str
    accession: str
    filed_date: date


class Event(_Strict):
    company_id: str
    form: str
    items: list[str] = Field(default_factory=list)  # e.g. ["4.01"]
    filed_date: date
    accession: str
    text_ref: str | None = None


class Point(_Strict):
    series_id: str
    value: float
    obs_date: date
    vintage_date: date


# ---- 6.1 AgentCall ----------------------------------------------------------

class Claim(_Strict):
    type: ClaimType
    question_id: str
    answer: str
    probability: float = Field(ge=0.0, le=1.0)


class EvidenceItem(_Strict):
    metric: str
    value: float
    as_of: date


class AgentCall(_Strict):
    call_id: str
    run_id: str
    agent: AgentName
    company_id: str = Field(pattern=r"^anon_\d{3}$")
    as_of: date
    horizon: Horizon
    claim: Claim
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: list[str] = Field(max_length=5)
    evidence: list[EvidenceItem]
    principles_used: list[str] = Field(default_factory=list)
    tool_calls: int = Field(ge=0, le=5)
    model: str


# ---- 6.2 Grade --------------------------------------------------------------

class Grade(_Strict):
    call_id: str
    graded_at: datetime
    resolution_date: date | None
    outcome: str  # yes | no | bull | base | bear | unresolvable
    correct: bool | None  # None when unresolvable
    brier: float | None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


# ---- 6.3 Correction ---------------------------------------------------------

class Correction(_Strict):
    correction_id: str
    call_id: str
    agent: AgentName
    company_id: str
    as_of: date
    predicted: dict[str, Any]  # {"answer", "probability"}
    actual: dict[str, Any]  # {"outcome", "evidence"}
    error_type: ErrorType
    lesson: str
    principle_refs: list[str] = Field(default_factory=list)
    inputs_snapshot: dict[str, Any] = Field(default_factory=dict)
