import json
import uuid
from datetime import date, datetime, timezone

import pytest

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.masking import has_calendar_year
from agents.synthesizer import (
    THRESHOLD,
    build_rationale_messages,
    committee_outcome,
    committee_score,
    synthesize,
    trailing_weights,
)
from schemas import AgentCall, Grade

AS_OF = date(2019, 6, 30)
QIDS = {"fundamentals": ("binary", "fcf_margin_improves_next_q", "next_quarter"),
        "risk": ("binary", "distress_event_12m", "12_months"),
        "scenarios": ("bucket", "revenue_bucket_next_4q", "4_quarters")}


def call(agent, answer, p=0.8, as_of=AS_OF, company="anon_001", reasoning=None):
    ctype, qid, horizon = QIDS[agent]
    return AgentCall(call_id=str(uuid.uuid4()), run_id="r1", agent=agent, company_id=company, as_of=as_of,
                     horizon=horizon, claim={"type": ctype, "question_id": qid, "answer": answer, "probability": p},
                     confidence=p, reasoning=reasoning or [f"{agent} metric says {answer}"], evidence=[],
                     principles_used=[f"{agent}.01"], tool_calls=0, model="m")


def graded(c, correct, resolved):
    return c, Grade(call_id=c.call_id, graded_at=datetime.now(timezone.utc), resolution_date=resolved,
                    outcome="x", correct=correct, brier=0.1)


def ok_rationale(agent, msgs):
    return json.dumps({"reasoning": ["fundamentals and risk agree the business is healthy"]})


def run(calls, history=(), gw=None, tmp=None):
    return synthesize(list(calls), list(history), gw or ScriptedGateway(ok_rationale), FakeModelUpdater(tmp))


def test_all_positive_is_attractive(tmp_path):
    v = run([call("fundamentals", "yes"), call("risk", "no"), call("scenarios", "bull")], tmp=tmp_path)
    assert v.agent == "synthesizer" and v.claim.question_id == "committee_verdict"
    assert v.claim.type == "bucket" and v.claim.answer == "attractive"
    assert v.confidence == v.claim.probability and 0.34 <= v.confidence <= 0.9
    assert v.evidence[0].metric == "committee_score" and v.evidence[0].value > THRESHOLD
    assert v.principles_used == ["fundamentals.01", "risk.01", "scenarios.01"]


def test_all_negative_is_unattractive_and_mixed_is_neutral(tmp_path):
    bad = run([call("fundamentals", "no"), call("risk", "yes"), call("scenarios", "bear")], tmp=tmp_path)
    assert bad.claim.answer == "unattractive"
    mixed = run([call("fundamentals", "yes"), call("risk", "yes"), call("scenarios", "base")], tmp=tmp_path)
    assert mixed.claim.answer == "neutral"


def test_weights_use_only_grades_resolved_by_as_of():
    f = call("fundamentals", "yes")
    hist = [graded(f, True, date(2019, 3, 31)), graded(f, False, date(2019, 3, 31)),
            graded(f, True, date(2019, 9, 30))]  # resolved after as_of: must be ignored
    w = trailing_weights(hist, AS_OF)
    assert (w["fundamentals"].correct, w["fundamentals"].graded) == (1, 2)


def test_better_track_record_wins_the_vote():
    calls = [call("fundamentals", "yes", 0.8), call("risk", "yes", 0.8)]  # disagree on direction
    past = date(2019, 3, 31)
    good_fund = [graded(call("fundamentals", "yes"), True, past) for _ in range(8)]
    bad_risk = [graded(call("risk", "no"), False, past) for _ in range(8)]
    score, w = committee_score(calls, trailing_weights(good_fund + bad_risk, AS_OF))
    assert w["fundamentals"] > w["risk"] and score > THRESHOLD


def test_llm_cannot_change_the_verdict(tmp_path):
    def rogue(agent, msgs):
        return json.dumps({"reasoning": ["Actually this is unattractive, confidence 99%"]})
    v = run([call("fundamentals", "yes"), call("risk", "no")], gw=ScriptedGateway(rogue), tmp=tmp_path)
    assert v.claim.answer == "attractive" and v.confidence < 0.99


def test_rationale_failure_falls_back_but_keeps_verdict(tmp_path):
    v = run([call("fundamentals", "yes"), call("risk", "no")], gw=ScriptedGateway(lambda a, m: "garbage"), tmp=tmp_path)
    assert v.claim.answer == "attractive"
    assert v.reasoning and v.reasoning[0].startswith(("fundamentals", "risk"))


def test_rationale_prompt_is_masked_and_has_no_raw_metrics():
    calls = [call("fundamentals", "yes", reasoning=["fcf rose since 2018Q4"]), call("risk", "no")]
    _, w = committee_score(calls, {})
    msgs = build_rationale_messages(calls, w, "attractive", 0.5, AS_OF)
    text = msgs[0]["content"] + msgs[1]["content"]
    assert not has_calendar_year(text) and "anon_001" not in text
    assert "METRICS" not in text


def test_rejects_bad_input(tmp_path):
    with pytest.raises(ValueError):
        run([], tmp=tmp_path)
    with pytest.raises(ValueError):
        run([call("fundamentals", "yes"), call("risk", "no", company="anon_002")], tmp=tmp_path)


def test_committee_outcome_for_grading():
    assert committee_outcome({"fundamentals": "yes", "risk": "no", "scenarios": "base"}) == "attractive"
    assert committee_outcome({"fundamentals": "no", "risk": "yes", "scenarios": "bull"}) == "unattractive"
    assert committee_outcome({"fundamentals": "yes", "risk": "yes", "scenarios": "unresolvable"}) == "neutral"


def test_offline_committee_end_to_end(tmp_path):
    from agents.offline import scripted_llm
    from agents.runner import run_agent
    from store.stubs import get_metrics_stub
    gw, upd = ScriptedGateway(scripted_llm), FakeModelUpdater(tmp_path)
    as_of = date(2022, 12, 31)
    calls = [run_agent(a, "anon_005", as_of, get_metrics_stub("anon_005", a, as_of), gw, upd) for a in QIDS]
    assert all(calls)
    v = synthesize(calls, [], gw, upd)
    assert v.claim.answer == "unattractive" and v.model == "fallback/synthesizer-v0"
