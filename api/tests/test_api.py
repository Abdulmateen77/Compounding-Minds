import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_service
from api.service import Service

client = TestClient(app)


@pytest.fixture(scope="module")
def svc():
    return Service(os.environ["DASHBOARD_SOURCE"])  # pinned by conftest.py


def test_health_and_companies():
    h = client.get("/api/health").json()
    assert h["ok"] and h["companies"] == 5
    assert h["stub"] is True and h["banner"].startswith("NOT RESULTS")
    ids = [c["id"] for c in client.get("/api/companies").json()]
    assert "anon_001" in ids and all(i.startswith("anon_") for i in ids)


def test_assessment_shape_and_labels():
    aid = client.post("/api/assessments", json={"company_id": "anon_001"}).json()["assessment_id"]
    a = client.get(f"/api/assessments/{aid}").json()
    assert a["label"] in {"investable", "watch", "not_investable"}
    assert set(a["votes"]) == {"for", "neutral", "against"}
    assert sum(a["votes"].values()) == len(a["committee"]) >= 3
    assert a["disclaimer"] == "Research tool, not financial advice."
    assert 0 <= a["confidence"] <= 1 and -1 <= a["score"] <= 1
    assert a["mubit"] and a["metrics"]


def test_no_buy_sell_language():
    aid = client.post("/api/assessments", json={"company_id": "anon_002"}).json()["assessment_id"]
    text = client.get(f"/api/assessments/{aid}").text.lower()
    assert "you should buy" not in text and "you should sell" not in text


def test_as_of_gate_no_future_data(svc):
    qs = svc.quarters_for("anon_001")
    early = qs[3]
    a = svc.assess("anon_001", early)
    assert all(date.fromisoformat(e.as_of) <= early for v in a.committee for e in v.evidence)
    for m in a.mubit:
        if m.last_correction:
            assert date.fromisoformat(m.last_correction.as_of) <= early


def test_unknown_company_and_date_404():
    assert client.post("/api/assessments", json={"company_id": "anon_999"}).status_code == 404
    assert client.post("/api/assessments", json={"company_id": "anon_001", "as_of": "1999-01-01"}).status_code == 404
    assert client.get("/api/assessments/garbage").status_code == 404


def test_sse_stream_ends_with_done():
    aid = client.post("/api/assessments", json={"company_id": "anon_001"}).json()["assessment_id"]
    body = client.get(f"/api/assessments/{aid}/events?pause=0").text
    names = [l.split(": ", 1)[1] for l in body.splitlines() if l.startswith("event: ")]
    assert names[0] == "stage" and names[-1] == "done"
    assert "verdict" in names and names.count("agent_call") >= 3


def test_track_record():
    r = client.get("/api/agents/risk/track-record").json()
    assert r["learned"] and len(r["learned"]) == len(r["quarters"])
    assert client.get("/api/agents/nobody/track-record").status_code == 404


def test_track_record_contract_and_as_of_gate():
    full = client.get("/api/agents/risk/track-record").json()
    keys = {"agent", "investor", "as_of", "learned", "frozen", "quarters", "model_version", "accuracy", "brier",
            "calls_graded", "corrections_applied", "last_correction", "fallback_updater"}
    assert keys <= set(full)
    early = full["quarters"][5]
    r = client.get(f"/api/agents/risk/track-record?as_of={early}").json()
    assert all(q <= early for q in r["quarters"]) and len(r["quarters"]) < len(full["quarters"])
    assert r["corrections_applied"] <= full["corrections_applied"]
    lc = full["last_correction"]
    assert lc and lc["lesson"] and lc["mubit_ref"] and lc["version_before"]
    assert client.get("/api/agents/risk/track-record?as_of=nope").status_code == 422


def test_evidence_values_have_accession_key():
    aid = client.post("/api/assessments", json={"company_id": "anon_001"}).json()["assessment_id"]
    a = client.get(f"/api/assessments/{aid}").json()
    for v in a["committee"]:
        for e in v["evidence"]:
            assert "accession" in e and isinstance(e["value"], (int, float))


def test_replay_run_in_progress(tmp_path):
    """grader.replay's tables (baseline arm, top-level held-out list), read while still being written."""
    from dashboard.tests.fixtures import write_replay_run
    s = Service(str(write_replay_run(tmp_path)))
    stub, banner = s.provenance()
    assert stub is False and banner is None  # Mubit lessons updater, no fallback
    assert {c.id: c.held_out for c in s.companies()} == {"anon_001": False, "anon_002": True}
    assert set(s.gc["arm"]) == {"learned", "frozen", "baseline"}
    tr = s.track_record("fundamentals")
    assert tr.last_correction and tr.last_correction.mubit_ref == "lessons:fundamentals:1"
    assert tr.last_correction.version_after.endswith("-lessons-v1") and tr.fallback_updater is False


def test_heldout_report_served_or_404(monkeypatch, tmp_path):
    from dashboard import data as D
    rep = {"agents": {"risk": {"segments": {}}}, "banner": None}
    (tmp_path / "heldout_report.json").write_text(__import__("json").dumps(rep))
    monkeypatch.setattr(D, "HELDOUT_CANDIDATES", (tmp_path / "heldout_report.json",))
    monkeypatch.setattr(D, "ROOT", tmp_path)
    r = client.get("/api/heldout")
    assert r.status_code == 200 and r.json() == {"path": "heldout_report.json", "report": rep}
    monkeypatch.setattr(D, "HELDOUT_CANDIDATES", (tmp_path / "missing.json",))
    assert client.get("/api/heldout").status_code == 404


def test_mubit_adapters_serves_the_console_reading_with_its_time(monkeypatch, tmp_path):
    import api.main as main
    d = client.get("/api/mubit/adapters").json()
    assert d["read_at"] and "by hand" in d["source"]
    for a in d["adapters"]:
        assert 0 <= a["matched"] <= 1 and 0 < a["target"] <= 1 and a["test_cases"] > 0
    for arm in ("before", "after"):
        assert all(0 <= d["agreement"][arm][k] <= 1 for k in ("fundamentals", "risk", "scenarios"))
    assert all(t["kept"] <= t["calls_7d"] for t in d["training"]["tasks"])
    monkeypatch.setattr(main, "MUBIT_CONSOLE", tmp_path / "missing.json")
    assert client.get("/api/mubit/adapters").status_code == 404


@pytest.mark.skipif(not (Path(__file__).resolve().parents[2] / "web" / "dist").is_dir(), reason="front end not built")
@pytest.mark.parametrize("path", ["..%2f..%2fCLAUDE.md", "%2e%2e/%2e%2e/CLAUDE.md", "assets/..%2f..%2f..%2fCLAUDE.md"])
def test_static_files_cannot_escape_dist(path):
    r = client.get(f"/{path}")
    assert not r.text.startswith("# CLAUDE.md")


def test_unknown_company_number_is_a_404_not_a_502(monkeypatch):
    from api import main
    from ingest.sec import NotFound as SecNotFound

    class Boom:
        def report(self, cik, force=False):
            raise SecNotFound("https://data.sec.gov/submissions/CIK0000000000.json")

    monkeypatch.setattr(main, "research_service", lambda: Boom())
    r = client.get("/api/research/company/0")
    assert r.status_code == 404 and "data.sec.gov" not in r.text
