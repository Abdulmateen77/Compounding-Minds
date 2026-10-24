"""Replay: smoke (1 company, 1 agent, 2 quarters, a correction), point-in-time grading, resume, cache version."""
import threading
import time
from datetime import date

from agents.cache import CachingGateway
from agents.frozen import FrozenUpdater
from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import demo_reality, scripted_llm
from agents.run_store import MemoryRunStore
from grader.replay import Replay, parse_quarters, resolve_by
from store.stubs import get_metrics_stub


def make(tmp_path, store=None, companies=("anon_001",), agents=("fundamentals",), held=(), workers=1, runner=None):
    store = store or MemoryRunStore()
    gw = ScriptedGateway(scripted_llm)
    ups = {"learned": FakeModelUpdater(tmp_path / "mem"), "frozen": FrozenUpdater()}
    rp = Replay(list(companies), list(agents), store, tag="t", gateways={"learned": gw, "frozen": gw},
                updaters=ups, outcome_fn=demo_reality, metrics_fn=get_metrics_stub,
                held_out_companies=list(held), state_path=tmp_path / "state.json", workers=workers, runner=runner)
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


# ---- concurrency: companies and agents within a quarter run in parallel, output is unchanged -------------

def _digest(store):
    """Everything a run wrote except the random ids, in write order."""
    calls = [(r["payload"]["agent"], r["payload"]["company_id"], r["payload"]["as_of"], r["payload"]["claim"]["answer"])
             for r in store.rows("calls")]
    grades = sorted((r["outcome"], r["correct"], round(r["brier"], 9)) for r in store.rows("grades"))
    snaps = [(r["run_id"], r["agent"], r["as_of"], r["n_calls"], r["accuracy"]) for r in store.rows("snapshots")]
    return calls, grades, snaps, len(store.rows("corrections"))


BIG = dict(companies=tuple(f"anon_{i:03d}" for i in range(1, 7)), agents=("fundamentals", "risk", "scenarios"))


def test_parallel_replay_is_identical_to_serial(tmp_path):
    a, sa, _ = make(tmp_path / "a", workers=1, **BIG)
    b, sb, _ = make(tmp_path / "b", workers=8, **BIG)
    qs = parse_quarters("2019Q1:2019Q4")
    ra, rb = a.run(qs, settle=4), b.run(qs, settle=4)
    assert (ra.n_calls, ra.n_graded, ra.n_corrections) == (rb.n_calls, rb.n_graded, rb.n_corrections)
    assert _digest(sa) == _digest(sb)


def test_model_calls_really_overlap_but_quarters_do_not(tmp_path):
    lock, state = threading.Lock(), {"now": 0, "peak": 0, "quarters_seen_together": False, "current": None}

    def runner(agent, company, as_of, *, metrics, gateway, updater, run_id):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
            if state["current"] not in (None, as_of) and state["now"] > 1:
                state["quarters_seen_together"] = True
            state["current"] = as_of
        time.sleep(0.02)
        with lock:
            state["now"] -= 1
        from grader.replay import stub_backed_runner
        return stub_backed_runner(agent, company, as_of, metrics=metrics, gateway=gateway, updater=updater, run_id=run_id)

    rp, _, _ = make(tmp_path, workers=6, runner=runner, **BIG)
    rp.run(parse_quarters("2019Q1:2019Q3"))
    assert state["peak"] > 1, "calls never ran in parallel"
    assert state["peak"] <= 6
    assert not state["quarters_seen_together"], "two quarters ran at the same time"


def test_one_failed_call_does_not_lose_the_others_and_the_run_can_resume(tmp_path):
    from grader.replay import stub_backed_runner
    boom = {"on": True}

    def runner(agent, company, as_of, **kw):
        if boom["on"] and company == "anon_003" and agent == "risk":
            raise RuntimeError("429 starter_credit_busy")
        return stub_backed_runner(agent, company, as_of, **kw)

    store = MemoryRunStore()
    rp, _, _ = make(tmp_path, store=store, workers=4, runner=runner, **BIG)
    qs = parse_quarters("2019Q2:2019Q2")
    try:
        rp.run(qs)
        raise AssertionError("the failure should have surfaced")
    except RuntimeError as e:
        assert "starter_credit_busy" in str(e)
    stored = [r for r in store.rows("calls") if r["run_id"] == "t-learned-train"]
    assert len(stored) == 6 * 3 - 1                       # every other call of the learned arm was kept
    boom["on"] = False
    rp.run(qs)                                            # resume: only the missing call is asked for
    assert len([r for r in store.rows("calls") if r["run_id"] == "t-learned-train"]) == 6 * 3


# ---- held-out companies: called and graded every quarter, never learned from -----------------------------

def test_heldout_companies_are_graded_but_never_become_lessons(tmp_path):
    held = ["anon_002", "anon_005"]
    rp, store, ups = make(tmp_path, held=held, **BIG)
    res = rp.run(parse_quarters("2019Q1:2020Q4"), settle=4)
    calls = {r["call_id"]: r["payload"] for r in store.rows("calls")}
    corr = store.rows("corrections")
    assert res.n_corrections > 0 and corr                       # learning really happened on the train names
    assert all(calls[c["call_id"]]["company_id"] not in held for c in corr)
    assert all(c["payload"]["company_id"] not in held for c in corr)
    lesson_ids = {r["correction_id"] for a in BIG["agents"] for r in ups["learned"]._rows(a)}
    assert lesson_ids == {c["correction_id"] for c in corr}     # the updater saw exactly those, nothing else
    graded = {r["call_id"] for r in store.rows("grades")}
    for cid in held:                                            # still called and graded, in the learned arm too
        mine = [k for k, p in calls.items() if p["company_id"] == cid and p["run_id"] == "t-learned-train"]
        assert mine and set(mine) & graded


# ---- a crash part-way through a quarter --------------------------------------------------------------------

def _jsonl_replay(tmp_path, runner=None):
    from agents.run_store import JsonlRunStore
    return make(tmp_path, store=JsonlRunStore(tmp_path / "store"), runner=runner, **BIG)


def test_crash_in_the_frozen_arm_resumes_without_relearning_or_redoing_the_learned_arm(tmp_path):
    from agents.frozen import FrozenUpdater as Frozen
    from grader.replay import stub_backed_runner
    qs = parse_quarters("2019Q1:2019Q4")
    clean, clean_store, clean_ups = _jsonl_replay(tmp_path / "clean")
    clean.run(qs)

    boom, asked = {"on": True}, []

    def runner(agent, company, as_of, **kw):
        frozen = isinstance(kw["updater"], Frozen)
        if boom["on"] and as_of == qs[2] and frozen:
            raise RuntimeError("529 overloaded")
        if as_of == qs[2] and not frozen:
            asked.append((agent, company))
        return stub_backed_runner(agent, company, as_of, **kw)

    rp, _, _ = _jsonl_replay(tmp_path / "crash", runner)
    try:
        rp.run(qs)
        raise AssertionError("the failure should have surfaced")
    except RuntimeError as e:
        assert "overloaded" in str(e)
    n_learned_q3 = len(asked)
    boom["on"] = False
    rp2, store2, ups2 = _jsonl_replay(tmp_path / "crash", runner)   # a new process: state.json + store on disk
    rp2.run(qs)
    assert n_learned_q3 > 0 and len(asked) == n_learned_q3   # the learned arm of that quarter was not asked again
    assert _digest(store2) == _digest(clean_store)           # same calls, grades, snapshots, corrections
    for a in BIG["agents"]:                                  # and no lesson was submitted twice
        assert ups2["learned"].get_model_version(a) == clean_ups["learned"].get_model_version(a)


def test_lessons_from_an_unsaved_quarter_are_set_aside_on_resume(tmp_path):
    import json
    rp, store, ups = _jsonl_replay(tmp_path)
    rp.run(parse_quarters("2019Q1:2019Q3"))
    before = ups["learned"].get_model_version("fundamentals")
    mem = ups["learned"]._mem("fundamentals")
    with mem.open("a") as f:                                 # what an older replay left after crashing mid-quarter
        f.write(json.dumps({"correction_id": "never-saved", "lesson": "x" * 30, "mubit_request_id": None}) + "\n")
    assert ups["learned"].get_model_version("fundamentals") != before
    rp2, _, ups2 = _jsonl_replay(tmp_path)
    assert ups2["learned"].get_model_version("fundamentals") == before
    assert "never-saved" in mem.with_name(mem.name + ".orphans").read_text()


def test_state_file_from_before_per_arm_saves_still_resumes(tmp_path):
    import json
    rp, store, _ = make(tmp_path)
    rp.run(parse_quarters("2019Q2:2019Q2"))
    (tmp_path / "state.json").write_text(json.dumps({"tag": "t", "done_quarters": ["2019-06-30"]}))
    rp2, _, _ = make(tmp_path, store=store)
    assert rp2.run(parse_quarters("2019Q2:2019Q2")).n_calls == 0
