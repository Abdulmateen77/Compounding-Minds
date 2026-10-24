"""Reply cache and Mubit batch runner. Fake gateways only: no network, no cost."""
import json
from datetime import date

import pytest

from agents.cache import CacheMiss, CachingGateway
from agents.gateway import ScriptedGateway
from agents.mubit_batch import AGENTS, build_cases, distinct, estimate, main, run_batch
from agents.offline import scripted_llm

MSGS = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hello"}]


class Inner(ScriptedGateway):
    """Counts live calls, can fail on demand, and mimics MubitGateway's request id."""

    def __init__(self, fn=lambda a, m: "reply", model="test-model"):
        super().__init__(fn)
        self.model, self.calls, self.fail, self.last_request_id = model, 0, False, None

    def complete(self, agent, messages, **kw):
        if self.fail:
            raise ConnectionError("boom")
        self.calls += 1
        self.last_request_id = f"mreq_{self.calls:032x}"
        return super().complete(agent, messages, **kw)


def test_second_identical_call_is_free_and_keeps_request_id(tmp_path):
    inner = Inner()
    gw = CachingGateway(inner, tmp_path)
    assert gw.complete("fundamentals", MSGS) == "reply"
    first_id = gw.last_request_id
    assert gw.complete("fundamentals", MSGS) == "reply"
    assert inner.calls == 1 and (gw.hits, gw.misses) == (1, 1)
    assert gw.last_request_id == first_id and first_id.startswith("mreq_")


def test_cache_survives_a_new_process(tmp_path):
    CachingGateway(Inner(), tmp_path).complete("fundamentals", MSGS)
    inner = Inner()
    assert CachingGateway(inner, tmp_path).complete("fundamentals", MSGS) == "reply"
    assert inner.calls == 0


def test_key_ignores_labels_but_not_content_model_or_options(tmp_path):
    gw = CachingGateway(Inner(), tmp_path)
    k = gw.key_for("fundamentals", MSGS)
    assert gw.key_for("fundamentals", MSGS, session_id="s1", purpose="reflection") == k
    assert gw.key_for("risk", MSGS) != k
    assert gw.key_for("fundamentals", [MSGS[0], {"role": "user", "content": "other"}]) != k
    assert gw.key_for("fundamentals", MSGS, max_tokens=5) != k
    assert CachingGateway(Inner(model="other-model"), tmp_path).key_for("fundamentals", MSGS) != k


def test_replay_only_blocks_live_calls_but_serves_saved_ones(tmp_path):
    CachingGateway(Inner(), tmp_path).complete("fundamentals", MSGS)
    inner = Inner()
    gw = CachingGateway(inner, tmp_path, replay_only=True)
    assert gw.complete("fundamentals", MSGS) == "reply"
    with pytest.raises(CacheMiss):
        gw.complete("fundamentals", [{"role": "user", "content": "never seen"}])
    assert inner.calls == 0


def test_refresh_goes_live_again_and_overwrites(tmp_path):
    inner = Inner(fn=lambda a, m: f"v{inner.calls}")
    CachingGateway(inner, tmp_path).complete("fundamentals", MSGS)          # v1
    assert CachingGateway(inner, tmp_path, refresh=True).complete("fundamentals", MSGS) == "v2"
    assert CachingGateway(inner, tmp_path).complete("fundamentals", MSGS) == "v2"


def test_failed_calls_are_not_cached(tmp_path):
    inner = Inner()
    gw = CachingGateway(inner, tmp_path)
    inner.fail = True
    with pytest.raises(ConnectionError):
        gw.complete("fundamentals", MSGS)
    inner.fail = False
    assert gw.complete("fundamentals", MSGS) == "reply" and inner.calls == 1
    assert list(tmp_path.glob("*.tmp")) == []


def test_cases_are_distinct_deterministic_and_labelled(tmp_path):
    gw = CachingGateway(Inner(), tmp_path)
    cases = build_cases(30)
    assert len(cases) == 90
    for agent in AGENTS:
        mine = [c for c in cases if c.agent == agent]
        assert len(mine) == 30 and sum(not c.synthetic for c in mine) == 5
    assert len(distinct(cases, gw)) == 90          # every prompt is different
    assert [c.metrics for c in build_cases(30)] == [c.metrics for c in cases]   # same run, same prompts


def test_jitter_keeps_integer_counts_and_changes_floats():
    base = {c.company_id: c for c in build_cases(5, ("risk",))}["anon_005"]
    syn = next(c for c in build_cases(12, ("risk",)) if c.synthetic and c.company_id == "anon_005")
    pick = lambda c, n: next(m["value"] for m in c.metrics["metrics"] if m["name"] == n)  # noqa: E731
    assert pick(syn, "going_concern_hits") == pick(base, "going_concern_hits")
    assert pick(syn, "interest_coverage") != pick(base, "interest_coverage")


def test_estimate_counts_live_vs_cached_and_prices_known_models(tmp_path):
    gw = CachingGateway(Inner(model="claude-haiku-4-5"), tmp_path)
    cases = distinct(build_cases(6, ("fundamentals",)), gw)
    e = estimate(cases, gw)
    assert (e.calls, e.cached, e.live) == (6, 0, 6) and e.usd and e.usd > 0
    gw.complete(cases[0].agent, cases[0].messages())     # cache one prompt
    e2 = estimate(cases, gw)
    assert (e2.cached, e2.live) == (1, 5) and e2.usd < e.usd
    assert estimate(cases, CachingGateway(Inner(model="mystery-model"), tmp_path)).usd is None


def test_run_batch_then_rerun_makes_zero_live_calls(tmp_path):
    inner = Inner(fn=scripted_llm)
    inner.complete = lambda agent, messages, **kw: (  # scripted_llm needs the real agent name
        setattr(inner, "calls", inner.calls + 1), scripted_llm(agent, messages))[1]
    gw = CachingGateway(inner, tmp_path)
    cases = build_cases(8)
    out = run_batch(cases, gw, log=lambda *_: None)
    assert out["sent"] == 24 and out["dropped"] == 0 and out["errors"] == 0 and inner.calls == 24
    out2 = run_batch(cases, gw, log=lambda *_: None)
    assert out2["sent"] == 24 and inner.calls == 24 and gw.hits == 24


def test_run_batch_stops_after_repeated_errors(tmp_path):
    inner = Inner()
    inner.fail = True
    out = run_batch(build_cases(8), CachingGateway(inner, tmp_path), max_consecutive_errors=3, log=lambda *_: None)
    assert out["errors"] == 3 and out["sent"] == 0


def test_cli_dry_run_spends_nothing_and_needs_no_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    assert main(["--per-agent", "6", "--cache-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN: nothing was sent" in out and "live calls to Mubit: 18" in out
    assert list(tmp_path.glob("*.json")) == []


def test_cli_live_refuses_over_the_cap(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    assert main(["--per-agent", "30", "--yes", "--max-calls", "10", "--cache-dir", str(tmp_path)]) == 2
    assert "refusing" in capsys.readouterr().out
