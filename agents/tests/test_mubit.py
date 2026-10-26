"""MubitGateway / MubitUpdater with a fake Anthropic client: no network, no credit spent."""
import itertools
from datetime import date
from types import SimpleNamespace

import pytest

from agents.correction_loop import run_correction_loop
from agents.cache import CachingGateway
from agents.gateway import (MAX_LESSONS_IN_PROMPT, DEFAULT_MAX_TOKENS, DEFAULT_MODEL, MAX_OUTPUT_TOKENS, MubitGateway, MubitUpdater,
                            ReplyTruncated)
from agents.offline import demo_reality, scripted_llm
from schemas import Correction

_ids = (f"mreq_{i:032x}" for i in itertools.count(1))


class FakeAnthropic:
    """Mimics client.messages.with_raw_response.create(...) -> raw with .headers and .parse()."""

    def __init__(self, reply_fn, stop_reasons=None):
        self.sent = []
        stops = iter(stop_reasons or [])
        outer = self

        class _Raw:
            def create(self, **params):
                outer.sent.append(params)
                msgs = [{"role": "system", "content": params["system"]}] + params["messages"]
                text = reply_fn("?", msgs)
                return SimpleNamespace(
                    headers={"x-middleware-request-id": next(_ids)},
                    parse=lambda: SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                                                  stop_reason=next(stops, "end_turn")))

        self.messages = SimpleNamespace(with_raw_response=_Raw())


def test_gateway_sends_anthropic_shape_and_records_request_id(monkeypatch):
    monkeypatch.delenv("MUBIT_MODEL", raising=False)  # .env may set it (api/main loads it)
    fake = FakeAnthropic(lambda a, m: "hello")
    gw = MubitGateway(client=fake)
    out = gw.complete("fundamentals",
                      [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}],
                      purpose="call", session_id="fundamentals:anon_001:2019-06-30")
    assert out == "hello"
    sent = fake.sent[0]
    assert sent["model"] == DEFAULT_MODEL and sent["system"] == "SYS"
    assert sent["messages"] == [{"role": "user", "content": "hi"}]
    assert sent["metadata"] == {"user_id": "fundamentals:anon_001:2019-06-30"}
    assert gw.last_request_id.startswith("mreq_")
    assert (gw.requests[0].agent, gw.requests[0].purpose) == ("fundamentals", "call")


def test_gateway_model_and_host_from_env(monkeypatch):
    monkeypatch.setenv("MUBIT_MODEL", "claude-sonnet-5-5")
    assert MubitGateway(client=FakeAnthropic(lambda a, m: "")).model == "claude-sonnet-5-5"


def test_gateway_without_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MUBIT_API_KEY"):
        MubitGateway()


def _correction(rid=None):
    return Correction(correction_id="c1", call_id="k1", agent="fundamentals", company_id="anon_001",
                      as_of=date(2019, 6, 30), predicted={"answer": "yes", "probability": 0.8},
                      actual={"outcome": "no", "evidence": []}, error_type="ignored_metric",
                      lesson="When capex_to_revenue is above 0.05, discount FCF calls.", principle_refs=["buffett.03"],
                      inputs_snapshot={"mubit_request_id": rid} if rid else {})


def test_updater_versions_lessons_and_links_mubit_request(tmp_path):
    upd = MubitUpdater(tmp_path, model="claude-haiku-5-5")
    assert upd.get_model_version("fundamentals") == "mubit:claude-haiku-5-5+fundamentals-lessons-v0"
    ref = upd.submit_corrections("fundamentals", [_correction("mreq_abc")])
    assert ref.ref == "mreq_abc" and ref.fallback is False
    assert upd.get_model_version("fundamentals").endswith("-lessons-v1")
    assert upd.status(ref).state == "applied"
    assert upd.lessons("fundamentals") == [_correction().lesson]
    assert upd.lessons("risk") == []  # per-agent isolation


def test_live_shaped_loop_with_fake_client(tmp_path):
    # the fake client doesn't know the agent name, so pin it for scripted_llm
    gw = MubitGateway(client=FakeAnthropic(lambda _a, m: scripted_llm("fundamentals", m)))
    upd = MubitUpdater(tmp_path, model=gw.model)
    res = run_correction_loop("fundamentals", "anon_001", date(2019, 6, 30), date(2019, 9, 30), gw, upd,
                              outcome_fn=demo_reality)
    assert res.before_grade.correct is False and res.after_grade.correct is True
    c = res.corrections[0]
    assert c.inputs_snapshot["mubit_request_id"].startswith("mreq_")
    assert res.update_ref.ref == c.inputs_snapshot["mubit_request_id"]
    assert res.version_after.endswith("fundamentals-lessons-v1")
    assert [r.purpose for r in gw.requests] == ["call", "reflection", "call"]
    sessions = [p["metadata"]["user_id"] for p in gw.client.sent]
    assert sessions[0].startswith("fundamentals:anon_001:") and sessions[1].startswith("reflection:")


# ---- output cap: a cut-off reply is retried with more room, never cached ---------------------------------

def test_default_cap_leaves_room_for_the_models_hidden_reasoning():
    fake = FakeAnthropic(lambda a, m: "{}")
    MubitGateway(client=fake).complete("risk", [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}])
    assert fake.sent[0]["max_tokens"] == DEFAULT_MAX_TOKENS >= 4096


def test_a_cut_off_reply_is_retried_with_a_bigger_cap():
    fake = FakeAnthropic(lambda a, m: "{}", stop_reasons=["max_tokens", "end_turn"])
    out = MubitGateway(client=fake).complete("risk", [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}])
    assert out == "{}" and [p["max_tokens"] for p in fake.sent] == [DEFAULT_MAX_TOKENS, MAX_OUTPUT_TOKENS]


def test_a_reply_still_cut_off_at_the_ceiling_raises_and_is_not_cached(tmp_path):
    fake = FakeAnthropic(lambda a, m: '{"claim": {"type', stop_reasons=["max_tokens"] * 10)
    cg = CachingGateway(MubitGateway(client=fake), tmp_path)
    with pytest.raises(ReplyTruncated):
        cg.complete("risk", [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}])
    assert fake.sent[-1]["max_tokens"] == MAX_OUTPUT_TOKENS
    assert list(tmp_path.glob("*.json")) == []          # nothing stored, so a re-run asks again


# ---- the prompt gets a rolling window of lessons; the version still counts them all -----------------------

def test_prompt_gets_the_most_recent_lessons_but_the_version_counts_every_one(tmp_path):
    up = MubitUpdater(tmp_path, model="m")
    n = MAX_LESSONS_IN_PROMPT + 15
    for i in range(n):
        up.submit_corrections("risk", [Correction(correction_id=f"c{i}", call_id=f"k{i}", agent="risk", company_id="anon_001",
                                                  as_of=date(2019, 6, 30), predicted={"answer": "no"}, actual={"outcome": "yes"},
                                                  error_type="wrong_signal", lesson=f"lesson number {i} " + "x" * 30)])
    got = up.lessons("risk")
    assert len(got) == MAX_LESSONS_IN_PROMPT == 40
    assert got[0].startswith("lesson number 15 ") and got[-1].startswith(f"lesson number {n - 1} ")   # newest kept, in order
    assert len(up.all_lessons("risk")) == n
    assert up.get_model_version("risk").endswith(f"-v{n}")                                             # not stuck at v40


# ---- record flag, system_sha, retries, ledger ------------------------------------------------------------

def _msgs(system="SYS"):
    return [{"role": "system", "content": system}, {"role": "user", "content": "u"}]


def test_recorded_calls_send_no_middleware_header_and_unrecorded_calls_send_record_off():
    fake = FakeAnthropic(lambda a, m: "ok")
    gw = MubitGateway(client=fake)
    gw.complete("risk", _msgs())
    gw.complete("risk", _msgs(), record=False)
    assert "extra_headers" not in fake.sent[0]
    assert fake.sent[1]["extra_headers"] == {"x-middleware-record": "off"}
    assert [r.recorded for r in gw.requests] == [True, False]
    assert all("x-middleware-store" not in str(p) for p in fake.sent)     # never set on any call


def test_request_carries_the_system_sha_that_keys_the_mubit_task():
    import hashlib
    gw = MubitGateway(client=FakeAnthropic(lambda a, m: "ok"))
    gw.complete("risk", _msgs("SYS"))
    assert gw.requests[0].system_sha == hashlib.sha256(b"SYS").hexdigest()[:12]


def test_unrecorded_flag_does_not_change_the_cache_key(tmp_path):
    cg = CachingGateway(MubitGateway(client=FakeAnthropic(lambda a, m: "ok")), tmp_path)
    assert cg.key_for("risk", _msgs()) == cg.key_for("risk", _msgs(), record=False)
    cg.complete("risk", _msgs(), record=False)
    cg.complete("risk", _msgs())
    assert (cg.misses, cg.hits) == (1, 1)


def test_real_client_is_built_with_four_retries(monkeypatch):
    import anthropic
    seen = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: seen.update(kw) or object())
    monkeypatch.setenv("MUBIT_LEDGER", "/dev/null")
    MubitGateway(api_key="k")
    assert seen["max_retries"] == 4 and seen["base_url"].endswith("/anthropic")


def test_ledger_counts_only_recorded_calls_per_task_per_day(tmp_path):
    from agents.ledger import CallLedger, report
    led = CallLedger(tmp_path / "ledger.jsonl")
    gw = MubitGateway(client=FakeAnthropic(lambda a, m: "ok"), ledger=led)
    for _ in range(3):
        gw.complete("risk", _msgs("A"))
    gw.complete("risk", _msgs("A"), record=False)
    gw.complete("fundamentals", _msgs("B"))
    per_task = led.recorded_per_task()
    assert sorted(per_task.values()) == [1, 3] and sum(per_task.values()) == 4
    lines = report(led)
    assert any("22 more until first training" in l for l in lines) and lines[-1].endswith(": 1")
    assert "request_id" in led.rows()[0] and "system_prompt" not in str(led.rows())   # ids and hashes only
