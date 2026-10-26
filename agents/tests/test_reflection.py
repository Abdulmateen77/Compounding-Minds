import json
import uuid
from datetime import date, datetime, timezone

from agents.correction_loop import run_correction_loop
from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import demo_reality, scripted_llm
from agents.reflection import (
    REFLECTION_TAG,
    GradedCall,
    build_reflection_messages,
    make_corrections,
    reflect,
    select_for_reflection,
)
from schemas import AgentCall, Grade
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)


def make_call(confidence=0.8, answer="yes", as_of=AS_OF, company="anon_001"):
    return AgentCall(
        call_id=str(uuid.uuid4()), run_id="r1", agent="fundamentals", company_id=company, as_of=as_of,
        horizon="next_quarter",
        claim={"type": "binary", "question_id": "fcf_margin_improves_next_q", "answer": answer, "probability": confidence},
        confidence=confidence, reasoning=["fcf_margin_qoq_change is rising"],
        evidence=[{"metric": "fcf_margin_qoq_change", "value": 0.006, "as_of": as_of}],
        principles_used=["buffett.01"], tool_calls=0, model="fallback/fundamentals-v0")


def make_grade(call, correct):
    outcome = call.claim.answer if correct else ("no" if call.claim.answer == "yes" else "yes")
    return Grade(call_id=call.call_id, graded_at=datetime.now(timezone.utc), resolution_date=None,
                 outcome=outcome, correct=correct, brier=0.64, evidence=[{"stub": True}])


def wrong_item(**kw):
    call = make_call(**kw)
    return GradedCall(call, make_grade(call, False), get_metrics_stub(call.company_id, "fundamentals", call.as_of))


def reply(**over):
    d = {"error_type": "ignored_metric",
         "lesson": "When capex_to_revenue is above 0.05, discount FCF improvement calls.",
         "principle_refs": ["buffett.03"]}
    d.update(over)
    return lambda agent, msgs: json.dumps(d)


def test_wrong_call_becomes_correction():
    item = wrong_item()
    c = reflect(item, ScriptedGateway(reply()))
    assert c is not None
    assert c.call_id == item.call.call_id and c.agent == "fundamentals"
    assert c.predicted == {"answer": "yes", "probability": 0.8}
    assert c.actual["outcome"] == "no"
    assert c.principle_refs == ["buffett.03"]
    assert c.inputs_snapshot["reasoning"] == item.call.reasoning


def test_correct_call_is_not_reflected():
    call = make_call()
    item = GradedCall(call, make_grade(call, True), get_metrics_stub("anon_001", "fundamentals", AS_OF))
    assert reflect(item, ScriptedGateway(reply())) is None


def test_reflection_prompt_hides_company_and_date():
    msgs = build_reflection_messages(wrong_item())
    text = msgs[0]["content"] + msgs[1]["content"]
    assert msgs[0]["content"].startswith(REFLECTION_TAG)
    assert "anon_001" not in text and "2019" not in text
    assert "ACTUAL OUTCOME (from later filings): no" in msgs[1]["content"]


def test_lesson_naming_company_or_year_is_rejected_after_repair():
    calls = []
    def leaky(agent, msgs):
        calls.append(1)
        return json.dumps({"error_type": "ignored_metric",
                           "lesson": "anon_001 in 2019 had capex_to_revenue too high.", "principle_refs": []})
    assert reflect(wrong_item(), ScriptedGateway(leaky)) is None
    assert len(calls) == 2  # one try + one repair


def test_bad_error_type_unknown_principle_or_uncited_lesson_rejected():
    assert reflect(wrong_item(), ScriptedGateway(reply(error_type="bad_luck"))) is None
    assert reflect(wrong_item(), ScriptedGateway(reply(principle_refs=["buffett.99"]))) is None
    assert reflect(wrong_item(), ScriptedGateway(reply(lesson="Be more careful about cash flow next time."))) is None


def test_repair_retry_can_recover():
    replies = iter(["not json", reply()("fundamentals", [])])
    assert reflect(wrong_item(), ScriptedGateway(lambda a, m: next(replies))) is not None


def test_selection_wrong_only_most_confident_first_capped_per_quarter():
    items = [wrong_item(confidence=p) for p in (0.6, 0.9, 0.7)]
    right = make_call(confidence=0.99)
    items.append(GradedCall(right, make_grade(right, True), {}))
    items.append(wrong_item(confidence=0.5, as_of=date(2019, 9, 30)))
    picked = select_for_reflection(items, cap=2)
    q2 = [it.call.confidence for it in picked if it.call.as_of == AS_OF]
    assert q2 == [0.9, 0.7]
    assert len(picked) == 3 and all(it.grade.correct is False for it in picked)


def test_make_corrections_routes_through_gateway_with_reflection_purpose():
    seen = []
    class Spy(ScriptedGateway):
        def complete(self, agent, messages, **kw):
            seen.append((agent, kw.get("purpose")))
            return super().complete(agent, messages, **kw)
    out = make_corrections([wrong_item()], Spy(reply()))
    assert len(out) == 1 and seen == [("fundamentals", "reflection")]


def test_end_to_end_loop_learns_and_bumps_version(tmp_path):
    res = run_correction_loop("fundamentals", "anon_001", AS_OF, date(2019, 9, 30),
                              ScriptedGateway(scripted_llm), FakeModelUpdater(tmp_path), outcome_fn=demo_reality)
    assert res.before_grade.correct is False
    assert len(res.corrections) == 1 and "capex_to_revenue" in res.corrections[0].lesson
    assert res.version_before == "fallback/fundamentals-v0"
    assert res.version_after == "fallback/fundamentals-v1" and res.update_ref.fallback
    assert res.after.model == "fallback/fundamentals-v1"
    assert res.after.claim.answer == "no" and res.after_grade.correct is True
    assert res.learned
    json.dumps(res.to_dict())  # serialisable for the dashboard


def test_loop_with_right_first_call_makes_no_update(tmp_path):
    # anon_004: FCF rising and low capex -> the naive "yes" is right under the stub rule
    res = run_correction_loop("fundamentals", "anon_004", date(2021, 9, 30), date(2021, 12, 31),
                              ScriptedGateway(scripted_llm), FakeModelUpdater(tmp_path), outcome_fn=demo_reality)
    assert res.before_grade.correct is True
    assert res.corrections == [] and res.update_ref is None
    assert res.version_after == res.version_before
