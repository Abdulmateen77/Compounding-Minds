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


# ---- research, memo and cross-exam prompts: same rule, checked through the real call paths ------------------

class _Capture:
    """Gateway that records every system prompt it is sent and answers with a fixed reply."""

    def __init__(self, reply: str):
        self.reply, self.systems = reply, []

    def complete(self, agent, messages, **kw):
        self.systems.append((agent, "\n\n".join(m["content"] for m in messages if m["role"] == "system")))
        return self.reply


def _lens(key: str, name: str, tag: str) -> dict:
    """A lens as research.analysis builds it, with checks that differ per company (`tag`)."""
    return {"key": key, "name": name, "question": f"Question {tag}?", "word": f"word {tag}", "fit": 0.5, "note": None,
            "checks": [{"id": "c1", "check": f"Check {tag}: ratio above {tag}", "result": "pass", "shown": f"{tag}.5x",
                        "principle": f"idea {tag}", "source": "a book"}]}


def _systems_by_agent(gw: _Capture) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for agent, system in gw.systems:
        out.setdefault(agent, set()).add(system_sha(system))
    return out


def test_narrative_and_chat_system_prompts_are_one_per_investor_whatever_the_company():
    from research import chat, narrative
    from research.analysis import INVESTORS

    narr, talk = _Capture('{"view": "v", "ahead": "a"}'), _Capture("Fine.")
    for company, tag, headline, news in (("Apple Inc.", "7", "Headline A", []), ("Coca-Cola Co.", "9", "Headline B", ["Some news line"])):
        for key, name, _q in INVESTORS:
            lens = _lens(key, name, tag)
            narrative.write(narr, lens, company, headline, [], news)
            chat.answer(talk, {"company": {"name": company}, "analysis": {}}, lens, f"Why {tag}?",
                        [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}])
    for gw in (narr, talk):
        by_agent = _systems_by_agent(gw)
        assert len(by_agent) == len(INVESTORS)                                   # one agent name per investor
        assert all(len(shas) == 1 for shas in by_agent.values()), by_agent       # and exactly one prompt each
        assert not any("Apple" in s or "Coca-Cola" in s for _, s in gw.systems)
    assert {s for shas in _systems_by_agent(narr).values() for s in shas}.isdisjoint(
        {s for shas in _systems_by_agent(talk).values() for s in shas})          # narrative and chat are different tasks


def test_news_summary_and_plans_chooser_system_prompts_are_constant():
    from research import text, web

    def news(tag):
        return {"items": [{"title": f"T{tag}", "url": f"https://x/{tag}", "source": f"s{tag}", "age": "1d", "age_days": 1,
                           "text": f"body {tag}"}]}

    gw = _Capture('{"items": []}')
    web.summarise(gw, "Apple Inc.", news("a"))
    web.summarise(gw, "Meta Platforms", news("b"))
    cands = lambda t: {"about": [f"About {t}."], "strategy": [f"Plan {t}."], "rnd": [f"R and D {t}."], "outlook": [f"Outlook {t}."]}
    text._choose(cands("a"), gw)
    text._choose(cands("b"), gw)
    by_agent = _systems_by_agent(gw)
    assert set(by_agent) == {"research_news", "research_text"} and all(len(v) == 1 for v in by_agent.values())


def test_memo_system_prompt_is_identical_across_companies_and_calls():
    from memos.memo import MemoInputs, build_messages as memo_messages

    def inputs(company, scale, as_of, calls):
        return MemoInputs(company, as_of, {"fundamentals": _bundle(scale, "capex_to_revenue")}, calls)

    one = memo_messages(inputs("anon_001", 1, A, [make_call()]))
    two = memo_messages(inputs("anon_042", 7, B, [make_call(answer="no", company="anon_042", as_of=B)]))
    assert _sha(one) == _sha(two) and one[1]["content"] != two[1]["content"]


def test_cross_exam_system_prompt_is_identical_across_cases():
    from agents.cross_exam import build_cross_messages

    a, b = make_call(company="anon_001"), make_call(answer="no", company="anon_009", as_of=B, confidence=0.6)
    one = build_cross_messages(a, [b], A)
    two = build_cross_messages(b, [a], B)
    assert _sha(one) == _sha(two) and one[1]["content"] != two[1]["content"]
