"""Mubit groups calls into a task by system prompt + model. If anything per-call leaks into a system prompt,
every call becomes its own task and the calls already sent are orphaned. These tests pin that."""
from datetime import date

import pytest

from agents.gateway import system_sha
from agents.reflection import build_reflection_messages
from agents.runner import build_messages
from agents.specs import SPECS
from agents.synthesizer import build_rationale_messages
from agents.tests.test_reflection import make_call, wrong_item

A = date(2019, 6, 30)
B = date(2023, 12, 31)


def _bundle(scale: float, extra: str) -> dict:
    return {"metrics": [{"name": "fcf_margin_qoq_change", "value": 0.006 * scale, "unit": "ratio"},
                        {"name": extra, "value": 1.5 * scale, "unit": "ratio"}]}


def _sha(msgs: list[dict]) -> str:
    return system_sha("\n\n".join(m["content"] for m in msgs if m["role"] == "system"))


@pytest.mark.parametrize("agent", sorted(SPECS))
def test_analyst_system_prompt_is_identical_across_companies_metrics_and_lessons(agent):
    one = build_messages(agent, "anon_001", A, _bundle(1, "capex_to_revenue"), [])
    two = build_messages(agent, "anon_042", B, _bundle(7, "net_debt_to_ebitda"),
                         ["When capex_to_revenue is above 0.05, discount FCF calls.", "A second lesson."])
    assert _sha(one) == _sha(two)
    assert one[1]["content"] != two[1]["content"]            # the differences did land in the user message
    assert "anon_042" in two[1]["content"] and "anon_042" not in two[0]["content"]


def test_reflection_system_prompt_is_identical_across_cases():
    a = build_reflection_messages(wrong_item(company="anon_001"))
    b = build_reflection_messages(wrong_item(company="anon_009", as_of=B, answer="no", confidence=0.55))
    assert _sha(a) == _sha(b)


def test_synthesizer_system_prompt_is_identical_across_verdicts():
    c1, c2 = make_call(answer="yes"), make_call(answer="no", company="anon_002", as_of=B)
    one = build_rationale_messages([c1], {"fundamentals": 1.0}, "buy-side lean", 0.4, A)
    two = build_rationale_messages([c1, c2], {"fundamentals": 0.3}, "neutral", -0.1, B)
    assert _sha(one) == _sha(two)


def test_system_sha_is_twelve_hex_chars_and_changes_with_the_prompt():
    assert len(system_sha("x")) == 12 and int(system_sha("x"), 16) >= 0
    assert system_sha("x") != system_sha("y")
