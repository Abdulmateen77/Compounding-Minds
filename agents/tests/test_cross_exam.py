import json
from datetime import date

from agents.cross_exam import MAX_SHIFT, cross_examine
from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import scripted_llm
from agents.runner import run_agent
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)


def calls(tmp_path):
    gw, upd = ScriptedGateway(scripted_llm), FakeModelUpdater(tmp_path)
    return [run_agent(a, "anon_001", AS_OF, get_metrics_stub("anon_001", a, AS_OF), gw, upd, "r")
            for a in ("fundamentals", "risk", "scenarios")]


def test_only_confidence_moves_and_originals_are_untouched(tmp_path):
    original = calls(tmp_path)
    before = [c.model_dump() for c in original]
    revised, record = cross_examine(original, ScriptedGateway(scripted_llm))
    assert [c.model_dump() for c in original] == before
    assert [c.claim.answer for c in revised] == [c.claim.answer for c in original]
    assert all(r.parsed for r in record) and any(r.revised_probability != r.original_probability for r in record)


def test_shift_is_capped_and_bad_replies_keep_the_original(tmp_path):
    original = calls(tmp_path)
    wild = ScriptedGateway(lambda a, m: json.dumps({"probability": 0.0, "challenge": "x"}))
    revised, _ = cross_examine(original, wild)
    for o, r in zip(original, revised):
        assert abs(o.claim.probability - r.claim.probability) <= MAX_SHIFT + 1e-9
    junk, rec = cross_examine(original, ScriptedGateway(lambda a, m: "no json"))
    assert [c.claim.probability for c in junk] == [c.claim.probability for c in original]
    assert not any(r.parsed for r in rec)


def test_single_call_is_left_alone(tmp_path):
    one = calls(tmp_path)[:1]
    assert cross_examine(one, ScriptedGateway(scripted_llm)) == (one, [])
