"""replay_runner: the function B's replay calls (--runner agents.entry:replay_runner)."""
import json
from datetime import date

import pytest

from agents import entry
from agents.entry import OUTCOMES, replay_runner
from agents.gateway import FakeModelUpdater, ScriptedGateway
from grader.replay import resolve_runner
from quality.frozen import FrozenUpdater
from schemas import Correction
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)


def reply(agent, messages):
    return json.dumps({"claim": {"type": "binary", "question_id": "x", "answer": "yes", "probability": 0.6},
                       "confidence": 0.6, "reasoning": ["fcf_margin_ttm is as shown"],
                       "evidence": [{"metric": "fcf_margin_ttm", "value": 0.142}], "principles_used": ["buffett.01"]})


@pytest.fixture(autouse=True)
def _counts():
    OUTCOMES.clear()


def run(updater, gateway, metrics=None):
    return replay_runner("fundamentals", "anon_001", AS_OF, metrics=metrics or get_metrics_stub("anon_001", "fundamentals", AS_OF),
                         gateway=gateway, updater=updater, run_id="r1")


def test_b_can_name_it_on_the_command_line():
    assert resolve_runner("agents.entry:replay_runner") is replay_runner


def test_it_returns_a_call_and_counts_it(tmp_path):
    call = run(FakeModelUpdater(tmp_path), ScriptedGateway(reply))
    assert call is not None and call.agent == "fundamentals" and call.run_id == "r1"
    assert OUTCOMES["ok"] == 1


def test_a_bundle_with_too_much_missing_is_skipped_and_the_model_is_never_asked(tmp_path):
    asked = []
    bundle = {**get_metrics_stub("anon_001", "fundamentals", AS_OF), "usable": False, "missing": ["a", "b", "c"]}
    assert run(FakeModelUpdater(tmp_path), ScriptedGateway(lambda a, m: asked.append(1) or "{}"), bundle) is None
    assert asked == [] and OUTCOMES["skipped"] == 1


def test_a_lesson_that_would_leak_blocks_the_call(tmp_path):
    asked = []
    result = replay_runner("fundamentals", "anon_001", AS_OF, metrics=get_metrics_stub("anon_001", "fundamentals", AS_OF),
                           gateway=ScriptedGateway(lambda a, m: asked.append(1) or reply(a, m)),
                           updater=_LessonUpdater(tmp_path, ["Tesla ignored capex, discount its FCF"]), run_id="r")
    assert result is None and asked == [] and OUTCOMES["blocked"] == 1


def test_an_invalid_reply_is_counted_as_dropped(tmp_path):
    assert run(FakeModelUpdater(tmp_path), ScriptedGateway(lambda a, m: "not json")) is None
    assert OUTCOMES["dropped"] == 1


class _LessonUpdater(FakeModelUpdater):
    """A fake updater that already holds lessons, as a learned arm does after some corrections."""
    def __init__(self, root, lessons):
        super().__init__(root)
        self._held = lessons

    def lessons(self, agent):
        return list(self._held)


def test_the_learned_arm_sees_its_lessons_and_the_frozen_arm_does_not(tmp_path):
    seen = {}

    def capture(name):
        def gw(agent, messages):
            seen[name] = messages[-1]["content"]
            return reply(agent, messages)
        return ScriptedGateway(gw)

    run(_LessonUpdater(tmp_path / "l", ["Discount FCF when capex intensity rises"]), capture("learned"))
    run(FrozenUpdater("base-model"), capture("frozen"))
    assert "Discount FCF when capex intensity rises" in seen["learned"]
    assert "Discount FCF when capex intensity rises" not in seen["frozen"]
    assert seen["learned"] != seen["frozen"]
