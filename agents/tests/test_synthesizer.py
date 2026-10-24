import json
import uuid
from datetime import date, datetime, timezone

import pytest

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.masking import has_calendar_year
from agents.synthesizer import (
    THRESHOLD,
    Calibration,
    build_rationale_messages,
    confidence_for,
    fit_calibration,
    grade_committee,
    verdict_for,
    committee_outcome,
    committee_score,
    synthesize,
    trailing_weights,
)
from agents.synthesizer import Weight
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


def test_weight_is_smoothed_trailing_accuracy_from_grades():
    h = [graded(call("fundamentals", "yes"), c, date(2019, 1, 1 + i)) for i, c in enumerate([True, True, False, True])]
    w = trailing_weights(h, AS_OF)["fundamentals"]
    assert (w.correct, w.graded) == (3, 4) and w.value == pytest.approx(4 / 6)


def test_weights_use_only_the_trailing_window_and_skip_unresolvable():
    h = [graded(call("risk", "no"), False, date(2018, 1, 1 + i)) for i in range(5)]
    h += [graded(call("risk", "no"), True, date(2019, 3, 1 + i)) for i in range(3)]
    h.append(graded(call("risk", "no"), None, date(2019, 4, 1)))
    w = trailing_weights(h, AS_OF, window=3)["risk"]
    assert (w.correct, w.graded) == (3, 3)


def test_score_is_weighted_by_track_record_and_computed_in_python():
    from agents.synthesizer import committee_score
    cs = [call("fundamentals", "yes", 0.8), call("risk", "yes", 0.8)]  # risk yes = distress = bad
    score, w = committee_score(cs, {"fundamentals": Weight(9, 10), "risk": Weight(1, 10)})
    assert w["fundamentals"] > w["risk"] and score > 0
    assert score == pytest.approx((w["fundamentals"] * 0.8 - w["risk"] * 0.8) / (w["fundamentals"] + w["risk"]))


def test_calibration_uses_empirical_hit_rate_per_band():
    pairs = [(0.9, True)] * 9 + [(0.9, False)] + [(0.05, True), (0.05, False)] * 5
    cal = fit_calibration(pairs)
    assert cal.confidence(0.9) > cal.confidence(0.05)
    assert cal.confidence(-0.9) == cal.confidence(0.9)  # sign does not matter
    assert confidence_for(0.9, cal) == cal.confidence(0.9)
    assert fit_calibration([]).confidence(0.9) == 0.5  # no data stays at the prior


def test_synthesize_uses_calibration_when_given(tmp_path):
    cal = Calibration(edges=(THRESHOLD,), rates=(0.4, 0.7))
    out = synthesize([call("fundamentals", "yes"), call("risk", "no")], [], ScriptedGateway(ok_rationale),
                     FakeModelUpdater(tmp_path), calibration=cal)
    assert out.claim.probability == 0.7 and out.claim.answer == "attractive"


def test_committee_graded_as_composite_of_underlying_outcomes(tmp_path):
    cs = [call("fundamentals", "yes"), call("risk", "no")]
    com = run(cs, tmp=tmp_path)
    good = [graded(cs[0], True, date(2019, 9, 30)), graded(cs[1], True, date(2020, 6, 30))]
    good = [(c, g.model_copy(update={"outcome": o})) for (c, g), o in zip(good, ["yes", "no"])]
    g = grade_committee(com, good)
    assert g.outcome == "attractive" and g.correct is True and g.resolution_date == date(2020, 6, 30)
    assert 0 <= g.brier < 0.5
    bad = [(c, gr.model_copy(update={"outcome": o})) for (c, gr), o in zip(good, ["no", "yes"])]
    assert grade_committee(com, bad).correct is False
    none = [(c, gr.model_copy(update={"correct": None, "outcome": "unresolvable"})) for c, gr in good]
    assert grade_committee(com, none).correct is None


def _quarter(company, as_of, answers, outcomes, resolved):
    """One (company, quarter): calls with the given answers, graded against the given outcomes."""
    rows = []
    for (agent, ans), out in zip(answers.items(), outcomes):
        c = call(agent, ans, 0.8, as_of=as_of, company=company)
        g = None if out is None else Grade(call_id=c.call_id, graded_at=datetime.now(timezone.utc),
                                           resolution_date=resolved, outcome=out, correct=out == ans, brier=0.1)
        rows.append((c, g))
    return rows


GOOD = {"fundamentals": "yes", "risk": "no", "scenarios": "bull"}


def test_calibration_pairs_are_point_in_time():
    from agents.synthesizer import calibration_pairs
    past, later = date(2018, 12, 31), date(2019, 3, 31)
    h = _quarter("anon_001", past, GOOD, ["yes", "no", "bull"], date(2019, 3, 31))     # right, resolved in time
    h += _quarter("anon_002", past, GOOD, ["no", "yes", "bear"], date(2019, 3, 31))    # wrong, resolved in time
    h += _quarter("anon_003", past, GOOD, ["yes", "no", "bull"], date(2019, 9, 30))    # resolves after as_of
    h += _quarter("anon_004", past, GOOD, ["yes", None, "bull"], date(2019, 3, 31))    # one call not graded yet
    h += _quarter("anon_005", later, GOOD, ["yes", "no", "bull"], date(2019, 3, 31))   # quarter not before as_of
    pairs = calibration_pairs(h, date(2019, 3, 31))
    assert sorted(hit for _, hit in pairs) == [False, True]
    assert all(s > THRESHOLD for s, _ in pairs)
    assert calibration_pairs(h, date(2019, 3, 31), exclude={"anon_002"}) == [p for p in pairs if p[1]]
    assert calibration_pairs(h, date(2019, 3, 31), fit_until=date(2018, 6, 30)) == []


def test_calibrate_needs_enough_pairs_then_reports_the_hit_rate():
    from agents.synthesizer import calibrate
    as_of, past = date(2021, 3, 31), date(2019, 12, 31)
    h = []
    for i in range(30):  # 24 right, 6 wrong, all confident
        h += _quarter(f"anon_{i + 1:03d}", past, GOOD,
                      ["yes", "no", "bull"] if i < 24 else ["no", "yes", "bear"], date(2020, 12, 31))
    cal, n = calibrate(h, as_of)
    assert n == 30 and cal is not None
    assert cal.confidence(0.6) == pytest.approx((24 + 1) / (30 + 2), abs=1e-3)
    assert calibrate(h, as_of, min_pairs=31) == (None, 30)
    v = synthesize([call("fundamentals", "yes", as_of=as_of), call("risk", "no", as_of=as_of)], [],
                   None, None, calibration=cal)
    assert v.claim.answer == "attractive" and v.claim.probability == cal.confidence(v.evidence[0].value)


def test_synthesize_without_gateway_is_pure_python():
    from agents.synthesizer import PYTHON_MODEL
    v = synthesize([call("fundamentals", "yes"), call("risk", "no")], [], None, None)
    assert v.model == PYTHON_MODEL and v.claim.answer == "attractive"
    assert v.reasoning[0].startswith(("fundamentals", "risk"))
