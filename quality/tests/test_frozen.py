"""The frozen twin never changes and never learns."""
from __future__ import annotations

import json
from datetime import date

from agents.gateway import FakeModelUpdater, ModelUpdater, ScriptedGateway, UpdateRef, UpdateStatus
from agents.runner import run_agent
from quality.frozen import FrozenUpdater, run_frozen
from schemas import Correction
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)


def correction(lesson="When capex_to_revenue rises, discount FCF improvement calls."):
    return Correction(correction_id="c1", call_id="k1", agent="fundamentals", company_id="anon_001", as_of=AS_OF,
                      predicted={"answer": "yes", "probability": 0.68}, actual={"outcome": "no", "evidence": []},
                      error_type="ignored_metric", lesson=lesson, principle_refs=["buffett.03"])


def reply(agent, messages):
    return json.dumps({"claim": {"type": "binary", "question_id": "x", "answer": "yes", "probability": 0.68},
                       "confidence": 0.68, "reasoning": ["fcf_margin_ttm is high"],
                       "evidence": [{"metric": "fcf_margin_ttm", "value": 0.142, "as_of": "2019-06-30"}],
                       "principles_used": ["buffett.01"]})


def test_it_is_a_model_updater_and_its_version_is_the_base_plus_frozen():
    u = FrozenUpdater(base="claude-haiku-4-5")
    assert isinstance(u, ModelUpdater)
    assert u.get_model_version("fundamentals") == "claude-haiku-4-5-frozen"


def test_the_version_never_changes_however_many_corrections_arrive():
    u = FrozenUpdater(base="m")
    before = u.get_model_version("fundamentals")
    for _ in range(5):
        u.submit_corrections("fundamentals", [correction(), correction("a different lesson")])
    assert u.get_model_version("fundamentals") == before == "m-frozen"
    assert u.get_model_version("risk") == "m-frozen"


def test_corrections_are_ignored_and_it_has_no_lessons():
    u = FrozenUpdater(base="m")
    ref = u.submit_corrections("fundamentals", [correction()])
    assert ref == UpdateRef("fundamentals", "frozen")
    assert u.lessons("fundamentals") == [] and u.lessons("risk") == []
    assert u.status(ref) == UpdateStatus("applied", "m-frozen")


def test_it_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    FrozenUpdater(base="m").submit_corrections("fundamentals", [correction()])
    assert list(tmp_path.iterdir()) == []


def test_run_frozen_makes_a_call_stamped_with_the_frozen_version():
    m = get_metrics_stub("anon_001", "fundamentals", AS_OF)
    call = run_frozen("fundamentals", "anon_001", AS_OF, m, ScriptedGateway(reply), run_id="r1",
                      updater=FrozenUpdater(base="m"))
    assert call is not None and call.model == "m-frozen" and call.run_id == "r1"
    assert call.claim.question_id == "fcf_margin_improves_next_q"


def test_the_frozen_twin_sees_the_same_prompt_as_a_learner_with_no_lessons_yet(tmp_path):
    """Same agent, same prompts: the only difference between the twins must be the lessons."""
    m = get_metrics_stub("anon_001", "fundamentals", AS_OF)
    seen = {}

    def capture(key):
        def fn(agent, messages):
            seen[key] = messages
            return reply(agent, messages)
        return fn

    run_frozen("fundamentals", "anon_001", AS_OF, m, ScriptedGateway(capture("frozen")))
    run_agent("fundamentals", "anon_001", AS_OF, m, ScriptedGateway(capture("fresh")), FakeModelUpdater(tmp_path))
    assert seen["frozen"] == seen["fresh"]


def test_lessons_cannot_reach_the_frozen_prompt_even_from_an_updater_that_has_them():
    class Leaky(FrozenUpdater):
        def lessons(self, agent):
            return ["SECRET LESSON the control must never see"]

    m = get_metrics_stub("anon_001", "fundamentals", AS_OF)
    prompts = []
    run_frozen("fundamentals", "anon_001", AS_OF, m,
               ScriptedGateway(lambda a, msgs: prompts.append(json.dumps(msgs)) or reply(a, msgs)), updater=Leaky())
    assert "SECRET LESSON" not in prompts[0]
    assert "(none yet)" in prompts[0]


def test_a_learning_updater_changes_its_version_but_the_frozen_one_does_not(tmp_path):
    learner, frozen = FakeModelUpdater(tmp_path), FrozenUpdater(base="m")
    for u in (learner, frozen):
        u.submit_corrections("fundamentals", [correction()])
    assert learner.get_model_version("fundamentals") == "fallback/fundamentals-v1"
    assert frozen.get_model_version("fundamentals") == "m-frozen"


def test_an_invalid_reply_is_dropped_like_any_other_call():
    m = get_metrics_stub("anon_001", "fundamentals", AS_OF)
    assert run_frozen("fundamentals", "anon_001", AS_OF, m, ScriptedGateway(lambda a, msgs: "not json")) is None
