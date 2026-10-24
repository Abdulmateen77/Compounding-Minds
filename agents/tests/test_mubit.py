"""MubitGateway / MubitUpdater with a fake Anthropic client: no network, no credit spent."""
import itertools
from datetime import date
from types import SimpleNamespace

import pytest

from agents.correction_loop import run_correction_loop
from agents.gateway import DEFAULT_MODEL, MubitGateway, MubitUpdater
from agents.offline import demo_reality, scripted_llm
from schemas import Correction

_ids = (f"mreq_{i:032x}" for i in itertools.count(1))


class FakeAnthropic:
    """Mimics client.messages.with_raw_response.create(...) -> raw with .headers and .parse()."""

    def __init__(self, reply_fn):
        self.sent = []
        outer = self

        class _Raw:
            def create(self, **params):
                outer.sent.append(params)
                msgs = [{"role": "system", "content": params["system"]}] + params["messages"]
                text = reply_fn("?", msgs)
                return SimpleNamespace(
                    headers={"x-middleware-request-id": next(_ids)},
                    parse=lambda: SimpleNamespace(content=[SimpleNamespace(type="text", text=text)]))

        self.messages = SimpleNamespace(with_raw_response=_Raw())


def test_gateway_sends_anthropic_shape_and_records_request_id():
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
