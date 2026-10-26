"""Adapter training: format rules, the real-data training set, the agreement score and per-company sessions.
Fake gateways and fake metrics only: no network, no database, no cost."""
import json
from datetime import date

from agents.agreement import measure, score_pair, summarise
from agents.gateway import system_sha
from agents.mubit_batch import Case, load_lessons, real_cases, run_batch, training_companies
from agents.runner import build_messages, principle_ids, rules_for
from agents.specs import SPECS

Q = date(2021, 6, 30)
BUNDLE = {"usable": True, "missing": [], "metrics": [{"name": "fcf_margin_qoq_change", "value": 0.0053, "unit": "ratio"},
                                                    {"name": "capex_to_revenue", "value": 0.04, "unit": "ratio"}]}


def reply(answer="yes", p=0.7, evidence=("fcf_margin_qoq_change", "capex_to_revenue"), principles=("buffett.01",),
          reasoning=("fcf_margin_qoq_change = 0.0053: momentum",), fence=False):
    body = json.dumps({"claim": {"type": "binary", "question_id": "fcf_margin_improves_next_q", "answer": answer,
                                 "probability": p}, "confidence": p, "reasoning": list(reasoning),
                       "evidence": [{"metric": m, "value": BUNDLE["metrics"][i]["value"]} for i, m in enumerate(evidence)],
                       "principles_used": list(principles)})
    return f"```json\n{body}\n```" if fence else body


# ---- format rules ---------------------------------------------------------------------------------------------

def test_format_rules_go_in_the_user_message_and_leave_the_task_key_alone():
    on = build_messages("fundamentals", "anon_001", Q, BUNDLE, [])
    off = build_messages("fundamentals", "anon_001", Q, BUNDLE, [], format_rules=False)
    assert system_sha(on[0]["content"]) == system_sha(off[0]["content"])
    assert all(f"FORMAT: {r}" in on[1]["content"] for r in rules_for("fundamentals"))
    assert '["buffett.01", "buffett.02", "buffett.03", "buffett.04", "buffett.05", "buffett.06"]' in on[1]["content"]
    assert "FORMAT:" not in off[1]["content"] and "FORMAT:" not in on[0]["content"]


def test_every_agent_has_principle_ids_for_its_rule():
    for agent, spec in SPECS.items():
        assert len(principle_ids(spec.principles_file)) >= 5, agent


def test_format_rules_do_not_trip_the_leak_check():
    from agents.leakcheck import find_leaks
    for agent in SPECS:
        assert find_leaks(build_messages(agent, "anon_001", Q, BUNDLE, [])[1]["content"]) == []


# ---- real-data training set -----------------------------------------------------------------------------------

def test_training_companies_leave_out_every_held_out_company():
    from ingest.universe import load_universe
    held = {c["company_id"] for c in load_universe() if c.get("held_out")}
    train = set(training_companies())
    assert held and train and not (held & train)


def test_real_cases_skip_unusable_bundles_and_carry_lessons(tmp_path):
    (tmp_path / "risk.jsonl").write_text("\n".join(json.dumps({"lesson": f"lesson {i}"}) for i in range(50)))
    seen = []

    def metrics_fn(company_id, agent, as_of):
        seen.append((company_id, as_of))
        return {**BUNDLE, "usable": company_id != "anon_bad"}

    quarters = [date(2019, 3, 31), date(2019, 6, 30), date(2019, 9, 30)]
    cases = real_cases(4, ("risk",), metrics_fn=metrics_fn, companies=["anon_001", "anon_bad", "anon_002"],
                       quarters=quarters, lessons_dir=tmp_path)
    assert len(cases) == 4 and all(c.company_id != "anon_bad" for c in cases)
    assert len({(c.company_id, c.as_of) for c in cases}) == 4                      # distinct prompts
    assert cases[0].lessons == tuple(f"lesson {i}" for i in range(10, 50))          # the 40 most recent
    assert "lesson 49" in cases[0].messages()[1]["content"]
    again = real_cases(4, ("risk",), metrics_fn=metrics_fn, companies=["anon_001", "anon_bad", "anon_002"],
                       quarters=quarters, lessons_dir=tmp_path)
    assert [(c.company_id, c.as_of) for c in again] == [(c.company_id, c.as_of) for c in cases]   # seeded


def test_missing_lesson_file_means_no_lessons(tmp_path):
    assert load_lessons(tmp_path, "scenarios") == () and load_lessons(None, "scenarios") == ()


def test_parallel_batch_sends_every_case_once_with_its_lessons():
    from agents.gateway import ScriptedGateway
    prompts = []

    def fn(agent, messages):
        prompts.append(messages[1]["content"])
        return reply()

    cases = [Case("fundamentals", f"anon_{i:03d}", Q, BUNDLE, False, ("apply this lesson",)) for i in range(12)]
    out = run_batch(cases, ScriptedGateway(fn), log=lambda *_: None, workers=4)
    assert out["sent"] == 12 and out["errors"] == 0 and out["dropped"] == 0
    assert len(prompts) == 12 and all("apply this lesson" in p for p in prompts)


# ---- agreement score ------------------------------------------------------------------------------------------

def test_identical_replies_match_and_a_fence_does_not_matter():
    s = score_pair(reply(), reply(fence=True))
    assert s.parsed and s.match and s.reasoning_jaccard == 1.0


def test_each_field_can_break_a_match():
    base = reply()
    assert not score_pair(base, reply(answer="no")).match
    assert not score_pair(base, reply(p=0.8)).match
    assert score_pair(base, reply(p=0.75)).match                                    # within 0.05
    assert not score_pair(base, reply(evidence=("fcf_margin_qoq_change",))).match
    assert not score_pair(base, reply(principles=("buffett.02",))).match
    assert score_pair(reply(principles=("a", "b", "c", "d")), reply(principles=("a", "b", "c"))).match   # 0.75
    assert score_pair(base, reply(reasoning=("totally different words",))).match   # wording never decides


def test_unparseable_reply_is_never_a_match():
    s = score_pair(reply(), "sorry, I cannot answer")
    assert not s.parsed and not s.match


def test_measure_sends_unrecorded_calls_and_summarises_per_agent():
    calls = []

    class Gw:
        def complete(self, agent, messages, **kw):
            calls.append(kw)
            return reply(p=0.7 if len(calls) % 2 else (0.9 if agent == "risk" else 0.7))

    cases = [Case(a, "anon_001", Q, BUNDLE, False) for a in ("fundamentals", "risk")]
    by_agent = measure(cases, Gw(), format_rules=True, workers=1)
    assert all(kw["record"] is False for kw in calls) and len(calls) == 4
    assert by_agent["fundamentals"]["match"] == 1.0 and by_agent["risk"]["match"] == 0.0
    assert summarise([])["match"] is None


# ---- research sessions ----------------------------------------------------------------------------------------

class _Sessions:
    def __init__(self, reply_text):
        self.reply, self.sessions = reply_text, []

    def complete(self, agent, messages, **kw):
        self.sessions.append(kw.get("session_id"))
        return self.reply


def _lens():
    return {"key": "buffett", "name": "Warren Buffett", "question": "Q?", "word": "w", "fit": 0.5, "note": None,
            "checks": [{"id": "c1", "check": "Check", "result": "pass", "shown": "1.5x", "principle": "idea", "source": "b"}]}


def test_research_calls_get_one_session_per_company_not_one_per_task():
    from research import chat, narrative, web
    narr, talk, news = _Sessions('{"view": "v", "ahead": "a"}'), _Sessions("Fine."), _Sessions('{"items": []}')
    item = {"items": [{"title": "T", "url": "https://x", "source": "s", "age": "1d", "age_days": 1, "text": "b"}]}
    for company in ("Apple Inc.", "Coca-Cola Co."):
        narrative.write(narr, _lens(), company, "Headline")
        chat.answer(talk, {"company": {"name": company}, "analysis": {}}, _lens(), "Why?")
        web.summarise(news, company, item)
    for gw in (narr, talk, news):
        assert len(set(gw.sessions)) == 2 and None not in gw.sessions, gw.sessions
