from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_service
from api.service import Service

client = TestClient(app)


@pytest.fixture(scope="module")
def svc():
    return Service("data/runs")


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
