import json
from datetime import date

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import scripted_llm
from agents.runner import run_agent
from agents.synthesizer import synthesize
from memos import MemoInputs, check_prose, write_memo
from memos.memo import _PLACEHOLDER
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)


def inputs(tmp_path):
    gw, upd = ScriptedGateway(scripted_llm), FakeModelUpdater(tmp_path)
    metrics = {a: get_metrics_stub("anon_001", a, AS_OF) for a in ("fundamentals", "risk", "scenarios")}
    calls = [run_agent(a, "anon_001", AS_OF, m, gw, upd, "r") for a, m in metrics.items()]
    return MemoInputs("anon_001", AS_OF, metrics, calls, synthesize(calls, [], gw, upd))


def test_check_prose():
    allowed = {"metric:risk.interest_coverage", "verdict"}
    assert check_prose("Coverage is {{metric:risk.interest_coverage}}; view {{verdict}}.", allowed) == []
    assert any("digit" in p for p in check_prose("Coverage is 12.4x.", allowed))
    assert any("unknown placeholder" in p for p in check_prose("{{metric:risk.made_up}}", allowed))
    assert any("advice" in p for p in check_prose("Investors should buy now.", allowed))


def test_memo_numbers_all_come_from_python(tmp_path):
    inp = inputs(tmp_path)
    memo = write_memo(inp, ScriptedGateway(scripted_llm))
    assert memo.prose_ok and "{{" not in memo.markdown
    assert "Research tool, not financial advice." in memo.markdown
    assert "anon_001" in memo.markdown and "| risk | interest_coverage | 12.40x |" in memo.markdown


def test_a_draft_with_numbers_is_repaired_once_then_dropped(tmp_path):
    inp = inputs(tmp_path)
    bad = json.dumps({"summary": "Margins hit 14.2% last year.", "views": "x", "risks": "y", "change": "z"})
    seen = []
    def fn(agent, messages):
        seen.append(1)
        return bad
    memo = write_memo(inp, ScriptedGateway(fn))
    assert len(seen) == 2 and not memo.prose_ok and memo.problems
    assert "failed the number check" in memo.markdown
    assert "14.2%" in memo.markdown  # from the Python metrics table, never from the draft
