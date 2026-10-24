from datetime import date, datetime, timezone

from agents.reflection import GradedCall
from grader.corrections import classify_error, make_corrections
from grader.tests.fixtures import call
from schemas import EvidenceItem, Grade

FQ = "fcf_margin_improves_next_q"


def graded(cid, conf, answer="yes", outcome="no", agent="fundamentals", res=date(2019, 8, 9),
           decisive=("operating_margin",), correct=None, evidence=(), reasoning=("x",), qid=FQ, ctype="binary"):
    c = call(qid, answer, prob=conf, agent=agent, call_id=cid, evidence=evidence, reasoning=reasoning,
             claim_type=ctype)
    ok = (answer == outcome) if correct is None else correct
    g = Grade(call_id=cid, graded_at=datetime.now(timezone.utc), resolution_date=res, outcome=outcome,
              correct=ok, brier=0.1, evidence=[{"decisive_metrics": list(decisive)}])
    return c, g


def test_cap_per_agent_per_quarter_highest_confidence_first():
    items = [graded(f"c{i:02d}", 0.5 + i / 100) for i in range(15)]
    items += [graded("risk1", 0.6, agent="risk", qid="distress_event_12m")]
    items += [graded("other-q", 0.9, res=date(2019, 11, 20))]
    out = make_corrections([GradedCall(c, g, {}) for c, g in items], cap=10)
    assert len(out) == 12  # fundamentals: 10 of 15 in 2019Q3 + 1 in 2019Q4; risk: 1
    q3_ids = [c.call_id for c in out if c.agent == "fundamentals"][:10]
    assert q3_ids == [f"c{i:02d}" for i in range(14, 4, -1)]  # c14 (0.64) ... c05


def test_only_misses_become_corrections():
    ok = graded("ok", 0.9, outcome="yes")
    un = graded("un", 0.9, outcome="unresolvable", correct=None)
    un[1].correct = None
    assert make_corrections([ok, un]) == []  # tuples work too


def test_error_types():
    # overconfident
    assert classify_error(*graded("a", 0.85)) == "overconfident"
    # missed regime: bull call, bear outcome
    c, g = graded("b", 0.6, answer="bull", outcome="bear", qid="revenue_bucket_next_4q", ctype="bucket", agent="scenarios")
    assert classify_error(c, g) == "missed_regime"
    # missed regime from a negative GDP snapshot
    assert classify_error(*graded("c", 0.6), metrics={"metrics": [{"name": "gdp_growth_yoy", "value": -0.03}]}) == "missed_regime"
    # ignored metric: the deciding metric is nowhere in reasoning/evidence
    assert classify_error(*graded("d", 0.6, reasoning=["fcf_margin_ttm is rising"])) == "ignored_metric"
    # wrong signal: it was cited, still wrong
    ev = [EvidenceItem(metric="operating_margin", value=0.1, as_of=date(2019, 6, 30))]
    assert classify_error(*graded("e", 0.6, evidence=ev)) == "wrong_signal"


def test_correction_shape_and_determinism():
    c, g = graded("z", 0.7)
    c = c.model_copy(update={"principles_used": ["buffett.03"]})
    out = make_corrections([GradedCall(c, g, {"metrics": [{"name": "operating_margin", "value": 0.1, "unit": "ratio"}]})])
    one = out[0]
    assert one.predicted == {"answer": "yes", "probability": 0.7} and one.actual["outcome"] == "no"
    assert one.principle_refs == ["buffett.03"] and one.inputs_snapshot["metrics"][0]["name"] == "operating_margin"
    assert make_corrections([(c, g)])[0].correction_id == one.correction_id


def test_replay_style_call_with_metrics_map_and_lesson_fn():
    c, g = graded("m", 0.7)
    out = make_corrections([(c, g)], metrics={"m": {"metrics": [{"name": "capex_to_revenue", "value": 0.05}]}},
                           lesson_fn=lambda call, gr, et: f"custom {et}")
    assert out[0].lesson.startswith("custom ") and out[0].inputs_snapshot["metrics"][0]["name"] == "capex_to_revenue"
