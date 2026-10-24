"""Response models for the investor UI (INVESTOR_UI_PLAN.md section 3).

The OpenAPI schema generated from these is the contract for web/ (types are generated, not hand-written).
Calls reuse the agent answer vocabulary; no number here is produced by an LLM.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Label = Literal["investable", "watch", "not_investable"]
Stance = Literal["for", "neutral", "against"]
Stage = Literal["ingest", "metrics", "committee", "cross_exam", "synthesis"]


class Company(BaseModel):
    id: str
    name: str  # render-time map only (api/display_names.json); falls back to the anon id
    sector: str | None = None
    held_out: bool = False


class EvidenceChip(BaseModel):
    metric: str
    value: float
    as_of: str
    accession: str | None = None  # filing accession when the stored run carries one (stubs: placeholder ids)


class AgentView(BaseModel):
    agent: str
    investor: str
    question: str
    answer: str
    probability: float
    confidence: float
    stance: Stance
    weight: float
    reasoning: list[str]
    evidence: list[EvidenceChip]
    principles: list[str]
    model: str
    revised_from: float | None = None
    # What reality said, from the reality grader (Python). None while the outcome is not settled yet.
    outcome: str | None = None
    correct: bool | None = None
    resolved_on: str | None = None   # filing date that settled it
    what_happened: str | None = None  # one plain sentence written by Python from the grader's evidence


class MetricCard(BaseModel):
    name: str
    value: float
    unit: str | None = None
    trend: list[float]  # oldest to newest, up to the as-of quarter
    accessions: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    bucket: str  # bull | base | bear
    probability: float
    reasoning: list[str]


class Correction(BaseModel):
    summary: str
    error_type: str | None
    as_of: str
    predicted: str | None
    actual: str | None
    mubit_ref: str | None
    applied: bool
    lesson: str | None = None
    principle_refs: list[str] = Field(default_factory=list)
    call_company: str | None = None
    version_before: str | None = None  # model that made the wrong call
    version_after: str | None = None   # first later model carrying the update
    reasked_answer: str | None = None  # same agent, same company, after the update


class MubitState(BaseModel):
    agent: str
    investor: str
    model_version: str | None
    accuracy: float | None
    calls_graded: int
    corrections_applied: int
    accuracy_trend: list[float]
    last_correction: Correction | None
    fallback_updater: bool  # lessons applied by the FakeModelUpdater, not Mubit (README 10)


class Votes(BaseModel):
    for_: int = Field(alias="for")
    neutral: int
    against: int
    model_config = {"populate_by_name": True}


class Assessment(BaseModel):
    assessment_id: str
    company: Company
    as_of: str
    label: Label
    verdict: str  # synthesizer verdict: attractive | neutral | unattractive
    score: float
    confidence: float
    votes: Votes
    summary: list[str]
    committee: list[AgentView]
    dissent: list[str]
    metrics: list[MetricCard]
    risks: list[str]
    scenarios: list[Scenario]
    mubit: list[MubitState]
    stub: bool
    banner: str | None
    disclaimer: str = "Research tool, not financial advice."


class StartRequest(BaseModel):
    company_id: str
    as_of: str | None = None  # defaults to the latest quarter with a full committee


class StartResponse(BaseModel):
    assessment_id: str


class Health(BaseModel):
    ok: bool
    source: str
    stub: bool
    banner: str | None
    companies: int
    quarters: list[str]


class TrackRecord(BaseModel):
    agent: str
    investor: str
    as_of: str
    learned: list[float]
    frozen: list[float]
    quarters: list[str]
    model_version: str | None = None
    accuracy: float | None = None
    brier: float | None = None
    calls_graded: int = 0
    corrections_applied: int = 0
    last_correction: Correction | None = None
    fallback_updater: bool = False
