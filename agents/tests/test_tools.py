import json
from datetime import date

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.runner import build_messages, run_agent
from agents.tools import MetricsToolbox, quarters_back
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)
M = get_metrics_stub("anon_001", "fundamentals", AS_OF)
FINAL = {"claim": {"type": "binary", "question_id": "x", "answer": "yes", "probability": 0.6},
         "confidence": 0.6, "reasoning": ["fcf_margin_ttm held up"], "principles_used": ["buffett.04"]}


def scripted(replies):
    seen = []
    def fn(agent, messages):
        seen.append(messages)
        return replies[min(len(seen) - 1, len(replies) - 1)]
    return fn, seen


def test_quarters_back():
    assert quarters_back(date(2019, 6, 30), 1) == date(2019, 3, 31)
    assert quarters_back(date(2019, 3, 31), 1) == date(2018, 12, 31)


def test_no_toolbox_means_the_prompt_is_unchanged(tmp_path):
    fn, seen = scripted([json.dumps({**FINAL, "evidence": [{"metric": "fcf_margin_ttm", "value": 0.142}]})])
    call = run_agent("fundamentals", "anon_001", AS_OF, M, ScriptedGateway(fn), FakeModelUpdater(tmp_path))
    assert call.tool_calls == 0 and seen[0] == build_messages("fundamentals", "anon_001", AS_OF, M, [])


def test_tool_call_then_answer_citing_the_tool_value(tmp_path):
    fn, seen = scripted([
        json.dumps({"tool": "get_metric_series", "args": {"metric": "fcf_margin_ttm", "n_quarters": 2}}),
        json.dumps({**FINAL, "evidence": [{"metric": "fcf_margin_ttm@Q-2", "value": 0.142}]}),
    ])
    tb = MetricsToolbox(get_metrics_stub, use_store=False)
    call = run_agent("fundamentals", "anon_001", AS_OF, M, ScriptedGateway(fn), FakeModelUpdater(tmp_path), toolbox=tb)
    assert call is not None and call.tool_calls == 1
    assert "TOOLS" in seen[0][1]["content"] and "TOOLS" not in seen[0][0]["content"]  # user message only
    assert "TOOL RESULT get_metric_series" in seen[1][-1]["content"] and "fcf_margin_ttm@Q-1" in seen[1][-1]["content"]


def test_tool_cap_is_enforced_and_errors_are_reported(tmp_path):
    ask = json.dumps({"tool": "nope", "args": {}})
    tb = MetricsToolbox(get_metrics_stub, use_store=False)
    fn, seen = scripted([ask] * 3 + [json.dumps({**FINAL, "evidence": []})])
    call = run_agent("fundamentals", "anon_001", AS_OF, M, ScriptedGateway(fn), FakeModelUpdater(tmp_path),
                     toolbox=tb, max_tool_calls=2)
    assert "TOOL ERROR nope" in seen[1][-1]["content"]
    assert "Tool limit reached" in seen[3][-1]["content"]
    assert call is not None and call.tool_calls == 2


def test_an_agent_that_keeps_asking_for_tools_is_dropped(tmp_path):
    fn, seen = scripted([json.dumps({"tool": "nope", "args": {}})])
    call = run_agent("fundamentals", "anon_001", AS_OF, M, ScriptedGateway(fn), FakeModelUpdater(tmp_path),
                     toolbox=MetricsToolbox(get_metrics_stub, use_store=False), max_tool_calls=2)
    assert call is None and len(seen) == 5  # 2 tools, limit notice, 1 repair, dropped


def test_tool_values_cannot_be_invented(tmp_path):
    fn, _ = scripted([json.dumps({**FINAL, "evidence": [{"metric": "fcf_margin_ttm@Q-1", "value": 0.9}]})])
    call = run_agent("fundamentals", "anon_001", AS_OF, M, ScriptedGateway(fn), FakeModelUpdater(tmp_path),
                     toolbox=MetricsToolbox(get_metrics_stub, use_store=False))
    assert call is None  # never fetched, so not citable


def test_series_only_reads_earlier_quarters():
    asked = []
    def metrics_fn(c, a, q):
        asked.append(q)
        return get_metrics_stub(c, a, q)
    MetricsToolbox(metrics_fn, use_store=False).call("get_metric_series", {"metric": "roic", "n_quarters": 3},
                                                     "anon_001", "fundamentals", AS_OF)
    assert asked and all(q < AS_OF for q in asked)
