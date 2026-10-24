"""Replay: smoke (1 company, 1 agent, 2 quarters, a correction), point-in-time grading, resume, cache version."""
from datetime import date

from agents.cache import CachingGateway
from agents.frozen import FrozenUpdater
from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import demo_reality, scripted_llm
from agents.run_store import MemoryRunStore
from grader.replay import Replay, parse_quarters, resolve_by
from store.stubs import get_metrics_stub


def make(tmp_path, store=None, companies=("anon_001",), agents=("fundamentals",), held=()):
    store = store or MemoryRunStore()
    gw = ScriptedGateway(scripted_llm)
    ups = {"learned": FakeModelUpdater(tmp_path / "mem"), "frozen": FrozenUpdater()}
    rp = Replay(list(companies), list(agents), store, tag="t", gateways={"learned": gw, "frozen": gw},
                updaters=ups, outcome_fn=demo_reality, metrics_fn=get_metrics_stub,
                held_out_companies=list(held), state_path=tmp_path / "state.json")
    return rp, store, ups


def test_parse_quarters():
    q = parse_quarters("2018Q1:2018Q4")
    assert q[0] == date(2018, 3, 31) and q[-1] == date(2018, 12, 31) and len(q) == 4
    assert parse_quarters("2019Q2,2019Q3") == [date(2019, 6, 30), date(2019, 9, 30)]


def test_smoke_two_quarters_with_correction(tmp_path):
    rp, store, ups = make(tmp_path)
    res = rp.run(parse_quarters("2019Q2:2019Q3"))
    assert res.n_calls == 6  # 3 arms x 2 quarters
    # quarter 1 calls are graded in quarter 2, never earlier
    snaps = [r for r in store.rows("snapshots") if r["variant"] == "learned"]
    by = {r["as_of"]: r for r in snaps}
    assert by["2019-06-30"]["n_calls"] == 0 and by["2019-09-30"]["n_calls"] == 1
    assert res.n_corrections == 1 and len(store.rows("corrections")) == 1
    assert ups["learned"].get_model_version("fundamentals").endswith("v1")
    assert ups["frozen"].get_model_version("fundamentals").endswith("v0")
    assert {r["kind"] for r in store.rows("runs")} == {"train"}


def test_no_learning_from_heldout_company_or_after_train_window(tmp_path):
    rp, store, ups = make(tmp_path, held=["anon_001"])
    assert rp.run(parse_quarters("2019Q2:2019Q3")).n_corrections == 0
    rp2, store2, ups2 = make(tmp_path / "b")
    res = rp2.run(parse_quarters("2023Q1:2023Q3"))
    assert res.n_graded > 0 and res.n_corrections == 0
    assert {r["kind"] for r in store2.rows("runs")} == {"heldout"}


def test_train_calls_resolving_after_train_end_are_not_learned_from(tmp_path):
    rp, store, ups = make(tmp_path)
    rp.run(parse_quarters("2022Q4:2022Q4"), settle=1)  # call 2022Q4, graded 2023Q1 (> train end)
    assert store.rows("corrections") == [] and len(store.rows("grades")) > 0


def test_resolve_by_uses_horizon():
    rp, store, _ = make(None or __import__("pathlib").Path(__import__("tempfile").mkdtemp()))
    rp.run(parse_quarters("2019Q2:2019Q2"))
    call = next(iter(rp.arms["learned"].calls.values()))
    assert resolve_by(call) == date(2019, 9, 30)


def test_resume_does_not_duplicate(tmp_path):
    rp, store, ups = make(tmp_path)
    rp.run(parse_quarters("2019Q2:2019Q3"))
    n_calls, n_corr = len(store.rows("calls")), len(store.rows("corrections"))
    rp2, _, _ = make(tmp_path, store=store)  # same store, same state file
    res = rp2.run(parse_quarters("2019Q2:2019Q3"))
    assert res.n_calls == 0 and len(store.rows("calls")) == n_calls and len(store.rows("corrections")) == n_corr


def test_cache_key_includes_model_version(tmp_path):
    class Inner(ScriptedGateway):
        model, calls = "m", 0
        def complete(self, agent, messages, **kw):
            self.calls += 1
            return "r"
    inner = Inner(lambda a, m: "r")
    ver = {"v": "v0"}
    gw = CachingGateway(inner, tmp_path, version_fn=lambda a: ver["v"])
    msgs = [{"role": "user", "content": "x"}]
    gw.complete("a", msgs); gw.complete("a", msgs)
    assert inner.calls == 1
    ver["v"] = "v1"  # a model update
    gw.complete("a", msgs)
    assert inner.calls == 2
    ver["v"] = "v0"  # old entry still valid for the old version
    gw.complete("a", msgs)
    assert inner.calls == 2


def _fingerprint(store):
    calls = sorted((r["agent"], r["company_id"], r["as_of"], r["run_id"]) for r in store.rows("calls"))
    grades = sorted((r["call_id"] is not None, r["outcome"]) for r in store.rows("grades"))
    return calls, grades, len(store.rows("corrections")), len(store.rows("snapshots"))


def test_running_model_calls_side_by_side_changes_nothing_about_the_result(tmp_path):
    """workers > 1 is only a speedup: the same calls, grades, corrections and snapshots as sequential."""
    seq_dir, par_dir = tmp_path / "seq", tmp_path / "par"
    seq_dir.mkdir(), par_dir.mkdir()
    cos, ags, quarters = ("anon_001", "anon_002", "anon_003", "anon_004"), ("fundamentals", "risk"), "2019Q1:2019Q4"
    rp1, s1, _ = make(seq_dir, companies=cos, agents=ags)
    rp1.workers = 1
    r1 = rp1.run(parse_quarters(quarters))
    rp2, s2, _ = make(par_dir, companies=cos, agents=ags)
    rp2.workers = 6
    r2 = rp2.run(parse_quarters(quarters))
    assert (r1.n_calls, r1.n_graded, r1.n_corrections, r1.dropped) == (r2.n_calls, r2.n_graded, r2.n_corrections, r2.dropped)
    assert r1.n_calls > 20
    assert _fingerprint(s1) == _fingerprint(s2)


def test_workers_default_comes_from_the_environment(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    monkeypatch.setenv("REPLAY_WORKERS", "5")
    assert make(tmp_path / "a")[0].workers == 5
    monkeypatch.delenv("REPLAY_WORKERS")
    assert make(tmp_path / "b")[0].workers == 1
