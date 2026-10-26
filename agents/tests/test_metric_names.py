"""Metric names must be copied exactly (Scenarios agent wrote `macro_beta` for `revenue_macro_beta`)."""
import json
from datetime import date

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.runner import build_messages, run_agent
from agents.specs import SPECS
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)


def scenarios_reply(metric_name):
    return json.dumps({
        "claim": {"type": "bucket", "question_id": "x", "answer": "base", "probability": 0.6},
        "confidence": 0.6, "reasoning": ["revenue_macro_beta is moderate"],
        "evidence": [{"metric": metric_name, "value": 0.8}], "principles_used": ["dalio.02"]})


def metrics():
    return get_metrics_stub("anon_001", "scenarios", AS_OF)


def test_scenarios_prompt_carries_the_exact_name_rule_in_the_user_message():
    msgs = build_messages("scenarios", "anon_001", AS_OF, metrics(), [])
    assert "RULE:" in msgs[1]["content"] and "revenue_macro_beta" in msgs[1]["content"]
    assert "RULE:" not in msgs[0]["content"]  # system prompt = Mubit's task key: must not change


def test_agents_without_extra_rules_keep_their_prompts_unchanged():
    for agent in ("fundamentals", "risk"):
        assert SPECS[agent].extra_rules == ()
        m = get_metrics_stub("anon_001", agent, AS_OF)
        assert "RULE:" not in build_messages(agent, "anon_001", AS_OF, m, [])[1]["content"]


def test_system_prompt_is_identical_with_and_without_rules():
    from dataclasses import replace
    with_rule = build_messages("scenarios", "anon_001", AS_OF, metrics(), [])[0]["content"]
    original = SPECS["scenarios"]
    try:
        SPECS["scenarios"] = replace(original, extra_rules=())
        assert build_messages("scenarios", "anon_001", AS_OF, metrics(), [])[0]["content"] == with_rule
    finally:
        SPECS["scenarios"] = original


def test_shortened_name_is_repaired_when_the_retry_lists_the_valid_names(tmp_path):
    seen = []

    def gw(agent, msgs):
        seen.append(msgs)
        if len(seen) == 1:
            return scenarios_reply("macro_beta")       # the original mistake
        # the repair prompt must name the right metric, otherwise the model can't fix it
        assert "revenue_macro_beta" in msgs[-1]["content"] and "not a metric name" in msgs[-1]["content"]
        return scenarios_reply("revenue_macro_beta")

    call = run_agent("scenarios", "anon_001", AS_OF, metrics(), ScriptedGateway(gw), FakeModelUpdater(tmp_path))
    assert call is not None and len(seen) == 2
    assert call.evidence[0].metric == "revenue_macro_beta"


def test_still_wrong_after_the_repair_is_dropped_not_guessed(tmp_path):
    calls = []
    gw = ScriptedGateway(lambda a, m: calls.append(1) or scenarios_reply("macro_beta"))
    assert run_agent("scenarios", "anon_001", AS_OF, metrics(), gw, FakeModelUpdater(tmp_path)) is None
    assert len(calls) == 2     # we never auto-correct the model's evidence


def test_wrong_value_error_states_the_exact_value(tmp_path):
    seen = []

    def gw(agent, msgs):
        seen.append(msgs)
        return json.dumps({**json.loads(scenarios_reply("revenue_macro_beta")),
                           "evidence": [{"metric": "revenue_macro_beta", "value": 9.9}]})

    run_agent("scenarios", "anon_001", AS_OF, metrics(), ScriptedGateway(gw), FakeModelUpdater(tmp_path))
    assert "must have the exact value 0.8" in seen[1][-1]["content"]
