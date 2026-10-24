"""Investor UI API (INVESTOR_UI_PLAN.md). Demo mode: replays stored runs, no live calls, no LLM.

    .venv/bin/uvicorn api.main:app --port 8000
    DASHBOARD_SOURCE=data/runs|data/runs_final|postgres to pick the data source (same switch as the
    Streamlit view; a relative directory resolves against the repo root).
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api import models as M
from api.service import NotFound, Service, get_service

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
STAGE_PAUSE = float(os.environ.get("API_STAGE_PAUSE", "0.7"))  # seconds between replayed events

app = FastAPI(title="Compounding Minds: investor API", version="0.1.0")


def _nf(e: NotFound) -> HTTPException:
    return HTTPException(404, str(e))


@app.get("/api/health", response_model=M.Health)
def health(s: Service = Depends(get_service)):
    stub, banner = s.provenance()
    return M.Health(ok=not s.bundle.empty, source=s.source, stub=stub, banner=banner,
                    companies=len(s.companies()), quarters=s.quarters())


@app.get("/api/companies", response_model=list[M.Company])
def companies(s: Service = Depends(get_service)):
    return s.companies()


@app.get("/api/companies/{company_id}/quarters", response_model=list[str])
def company_quarters(company_id: str, s: Service = Depends(get_service)):
    try:
        s.company(company_id)
    except NotFound as e:
        raise _nf(e)
    return [q.isoformat() for q in s.quarters_for(company_id)]


@app.post("/api/assessments", response_model=M.StartResponse)
def start(req: M.StartRequest, s: Service = Depends(get_service)):
    try:
        a = s.assess(req.company_id, date.fromisoformat(req.as_of) if req.as_of else None)
    except NotFound as e:
        raise _nf(e)
    except ValueError:
        raise HTTPException(422, "as_of must be YYYY-MM-DD")
    return M.StartResponse(assessment_id=a.assessment_id)


def _assess(s: Service, assessment_id: str) -> M.Assessment:
    try:
        cid, d = s.parse_id(assessment_id)
        return s.assess(cid, d)
    except NotFound as e:
        raise _nf(e)


@app.get("/api/assessments/{assessment_id}", response_model=M.Assessment, response_model_by_alias=True)
def get_assessment(assessment_id: str, s: Service = Depends(get_service)):
    return _assess(s, assessment_id)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/assessments/{assessment_id}/events")
async def events(assessment_id: str, pause: float = Query(STAGE_PAUSE, ge=0, le=5), s: Service = Depends(get_service)):
    a = _assess(s, assessment_id)

    async def gen():
        async def beat(mult: float = 1.0):
            if pause:
                await asyncio.sleep(pause * mult)

        for stage, detail in (("ingest", "Reading filings (point-in-time, cached)"),
                              ("metrics", f"{len(a.metrics)} metrics computed in Python")):
            yield _sse("stage", {"stage": stage, "status": "start", "detail": detail}); await beat(1.2)
            yield _sse("stage", {"stage": stage, "status": "done", "detail": detail}); await beat(0.3)
        yield _sse("stage", {"stage": "committee", "status": "start", "detail": "Investors make their calls"})
        for v in a.committee:
            await beat()
            yield _sse("agent_call", v.model_dump(by_alias=True))
        yield _sse("stage", {"stage": "committee", "status": "done", "detail": "All calls in"}); await beat(0.6)
        if any(v.revised_from is not None for v in a.committee):
            yield _sse("stage", {"stage": "cross_exam", "status": "done", "detail": "Confidence revised after peer review"}); await beat()
        yield _sse("stage", {"stage": "synthesis", "status": "start", "detail": "Weighting by track record"}); await beat(1.2)
        yield _sse("verdict", {"label": a.label, "score": a.score, "confidence": a.confidence,
                               "votes": a.votes.model_dump(by_alias=True)})
        yield _sse("stage", {"stage": "synthesis", "status": "done", "detail": "Verdict ready"})
        yield _sse("done", {"assessment_id": a.assessment_id})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/agents/{agent}/track-record", response_model=M.TrackRecord)
def track_record(agent: str, as_of: str | None = Query(None), s: Service = Depends(get_service)):
    try:
        return s.track_record(agent, date.fromisoformat(as_of) if as_of else None)
    except NotFound as e:
        raise _nf(e)
    except ValueError:
        raise HTTPException(422, "as_of must be YYYY-MM-DD")


@app.get("/api/heldout")
def heldout():
    """The held-out report (eval/reports/heldout_report.json, else the stub preview with its banner), as written."""
    from dashboard.data import ROOT, find_heldout_report
    path, report, why = find_heldout_report()
    if report is None:
        raise HTTPException(404, f"no held-out report yet ({why})")
    return {"path": str(path.relative_to(ROOT)), "report": report}


# ---- research on any listed company, as it stands today (research/) ----------------------------------------------
_research = None


def research_service():
    """Built on first use: it opens the SEC client, which needs SEC_USER_AGENT."""
    global _research
    if _research is None:
        from research.service import ResearchService
        _research = ResearchService()
    return _research


@app.get("/api/research/search")
def research_search(q: str = Query("", max_length=80)):
    try:
        return research_service().search(q)
    except Exception as e:
        raise HTTPException(502, f"Could not search the SEC company list: {e}")


@app.get("/api/research/evidence")
def research_evidence():
    """The back-test summary: how the investor checks did against what happened next (research/backtest.py)."""
    from research.backtest import EVIDENCE
    if not EVIDENCE.exists():
        raise HTTPException(404, "no back-test summary yet: run python -m research.backtest --write-evidence")
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


@app.get("/api/research/company/{cik}")
def research_company(cik: int, refresh: bool = False):
    try:
        return research_service().report(cik, force=refresh)
    except Exception as e:
        raise HTTPException(502, f"Could not build the report: {e}")


# Built front end (npm run build in web/). Absent in dev, where Vite serves the UI and proxies /api.
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
