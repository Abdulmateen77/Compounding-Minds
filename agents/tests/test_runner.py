import json
from datetime import date

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.runner import build_messages, run_agent
from grader.grade import grade
from schemas import Correction
from store.stubs import get_metrics_stub, list_stub_cases


def good_reply(agent, messages):
    return json.dumps({
        "claim": {"type": "binary", "question_id": "x", "answer": "yes", "probability": 0.68},
        "confidence": 0.68,
        "reasoning": ["fcf_margin_ttm is high and rising"],
        "evidence": [{"metric": "fcf_margin_ttm", "value": 0.142, "as_of": "2019-06-30"}],
        "principles_used": ["buffett.01"],
    })


def test_stub_cases_exist_for_every_mvp_agent():
    for a in ("fundamentals", "risk", "scenarios"):
        assert len(list_stub_cases(a)) == 5


def test_good_call_parses_and_grades(tmp_path):
    upd = FakeModelUpdater(tmp_path)
    m = get_metrics_stub("anon_001", "fundamentals", date(2019, 6, 30))
    call = run_agent("fundamentals", "anon_001", date(2019, 6, 30), m, ScriptedGateway(good_reply), upd)
    assert call and call.claim.question_id == "fcf_margin_improves_next_q"
    g = grade(call)
    assert g.brier is not None and g.outcome in ("yes", "no")


def test_invalid_json_gets_one_repair_then_drops(tmp_path):
    calls = []
    def bad(agent, msgs):
        calls.append(1); return "not json"
    m = get_metrics_stub("anon_001", "fundamentals", date(2019, 6, 30))
    assert run_agent("fundamentals", "anon_001", date(2019, 6, 30), m, ScriptedGateway(bad), FakeModelUpdater(tmp_path)) is None
    assert len(calls) == 2


def test_evidence_mismatch_is_rejected(tmp_path):
    def liar(agent, msgs):
        d = json.loads(good_reply(agent, msgs)); d["evidence"][0]["value"] = 0.9; return json.dumps(d)
    m = get_metrics_stub("anon_001", "fundamentals", date(2019, 6, 30))
    assert run_agent("fundamentals", "anon_001", date(2019, 6, 30), m, ScriptedGateway(liar), FakeModelUpdater(tmp_path)) is None


def test_prompt_carries_only_anon_id():
    m = get_metrics_stub("anon_001", "fundamentals", date(2019, 6, 30))
    msgs = build_messages("fundamentals", "anon_001", date(2019, 6, 30), m, [])
    assert "anon_001" in msgs[1]["content"]


def test_correction_changes_model_version_and_prompt(tmp_path):
    upd = FakeModelUpdater(tmp_path)
    assert upd.get_model_version("fundamentals") == "fallback/fundamentals-v0"
    c = Correction(correction_id="c1", call_id="k1", agent="fundamentals", company_id="anon_001",
                   as_of=date(2019, 6, 30), predicted={"answer": "yes", "probability": 0.68},
                   actual={"outcome": "no", "evidence": []}, error_type="ignored_metric",
                   lesson="When capex_to_revenue rises, discount FCF improvement calls.", principle_refs=["buffett.03"])
    ref = upd.submit_corrections("fundamentals", [c])
    assert ref.fallback and upd.get_model_version("fundamentals") == "fallback/fundamentals-v1"
    m = get_metrics_stub("anon_001", "fundamentals", date(2019, 9, 30))
    msgs = build_messages("fundamentals", "anon_001", date(2019, 9, 30), m, upd.lessons("fundamentals"))
    assert "capex_to_revenue rises" in msgs[0]["content"]
