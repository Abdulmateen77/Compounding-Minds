import json
from datetime import date

import pytest

from agents.frozen import FrozenUpdater
from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import demo_reality, scripted_llm
from eval.harness import evaluate_agent, planned_calls, resolve_by, summarise
from eval.report import build_report, render_markdown, write_report
from eval.split import make_split

SPLIT = make_split([f"anon_{i:03d}" for i in range(1, 6)], 1)
GW = ScriptedGateway(scripted_llm)


def run(tmp_path, agent="fundamentals", outcome_fn=demo_reality):
    learned = FakeModelUpdater(tmp_path / "mem")
    ev = evaluate_agent(agent, SPLIT, GW, learned, FrozenUpdater("m"), outcome_fn=outcome_fn)
    return ev, learned


def test_learning_happens_only_in_train_and_frozen_never_learns(tmp_path):
    ev, learned = run(tmp_path)
    assert ev.corrections_applied > 0
    assert ev.learned_version_end != ev.learned_version_start
    # No lessons were added during the held-out phase: version at the end equals what training produced.
    assert learned.get_model_version("fundamentals") == ev.learned_version_end
    assert ev.frozen_version.startswith("frozen:")
    frozen_calls = [c.call for c in ev.cells if c.arm == "frozen" and c.call]
    assert frozen_calls and all(c.model == ev.frozen_version for c in frozen_calls)


def test_late_resolving_calls_are_never_learned_from(tmp_path):
    # Everything resolves after the train window ends, so there is nothing legitimate to learn from.
    def late(call):
        return "no", {"resolution_date": "2023-06-30"}
    ev, _ = run(tmp_path, outcome_fn=late)
    assert ev.corrections_applied == 0 and ev.train_outcomes == []
    assert ev.learned_version_end == ev.learned_version_start


def test_corrections_wait_until_the_outcome_is_visible(tmp_path):
    # Every call resolves one year after it is made. A correction may only be submitted once
    # that resolution date has passed in the replay.
    from eval.split import add_quarters
    clock = {"q": None}

    def metrics(company, agent, q):
        clock["q"] = q
        from store.stubs import get_metrics_stub
        return get_metrics_stub(company, agent, q)

    def slow(call):
        return "no", {"resolution_date": date(call.as_of.year + 1, call.as_of.month, call.as_of.day).isoformat()}

    submitted = []

    class Spy(FakeModelUpdater):
        def submit_corrections(self, agent, corrections):
            for c in corrections:
                due = date(c.as_of.year + 1, c.as_of.month, c.as_of.day)
                # submitted at the start of quarter q, before q's metrics are read: clock is q-1
                assert due <= add_quarters(clock["q"], 1), (c.as_of, clock["q"])
                submitted.append(c)
            return super().submit_corrections(agent, corrections)

    evaluate_agent("fundamentals", SPLIT, GW, Spy(tmp_path / "mem"), FrozenUpdater("m"),
                   metrics_fn=metrics, outcome_fn=slow)
    assert submitted, "expected at least one correction to be learned inside the train window"


def test_dirty_memory_is_refused(tmp_path):
    learned = FakeModelUpdater(tmp_path / "mem")
    (tmp_path / "mem" / "fundamentals.jsonl").write_text(json.dumps({"correction_id": "x", "lesson": "old", "mubit_request_id": None}) + "\n")
    with pytest.raises(RuntimeError):
        evaluate_agent("fundamentals", SPLIT, GW, learned, FrozenUpdater("m"), outcome_fn=demo_reality)


def test_summary_pairs_cells_and_splits_segments(tmp_path):
    ev, _ = run(tmp_path)
    s = summarise(ev)
    seg = s["segments"]
    assert seg["all_companies"]["n"] == seg["seen_companies"]["n"] + seg["unseen_companies"]["n"] == 5 * 8
    assert seg["unseen_companies"]["n"] == 1 * 8
    d = seg["all_companies"]["learned_minus_frozen"]
    f, l = seg["all_companies"]["frozen"], seg["all_companies"]["learned"]
    assert d["accuracy"] == pytest.approx(l["accuracy"] - f["accuracy"])
    assert set(seg["all_companies"]["baselines"]) == {"always_yes", "base_rate"}


def test_unresolvable_cells_are_excluded(tmp_path):
    ev, _ = run(tmp_path, outcome_fn=lambda c: ("unresolvable", {}))
    s = summarise(ev)
    assert s["segments"]["all_companies"]["n"] == 0 and s["segments"]["all_companies"]["frozen"]["accuracy"] is None


def test_planned_calls():
    p = planned_calls(SPLIT, 3)
    assert p["per_agent_train"] == 4 * 20 and p["per_agent_held_out"] == 2 * 5 * 8


def test_report_banner_markdown_and_write_once(tmp_path):
    ev, _ = run(tmp_path)
    agents = {"fundamentals": summarise(ev)}
    stub = build_report(SPLIT, agents, {"real_results": False})
    assert "NOT RESULTS" in stub["banner"] and "NOT RESULTS" in render_markdown(stub)
    real = build_report(SPLIT, agents, {"real_results": True})
    assert real["banner"] is None
    js, md = write_report(real, tmp_path / "out")
    assert js.exists() and md.exists() and "Research tool, not financial advice" in md.read_text()
    with pytest.raises(FileExistsError):
        write_report(real, tmp_path / "out")
    write_report(real, tmp_path / "out", force=True)


def test_frontier_arm_curves_and_saving(tmp_path):
    from agents.run_store import MemoryRunStore
    from eval.harness import Arm, snapshots
    store = MemoryRunStore()
    store.start_run("t", "train"); store.start_run("h", "heldout")
    ev = evaluate_agent("fundamentals", SPLIT, GW, FakeModelUpdater(tmp_path / "mem"), FrozenUpdater("m"),
                        outcome_fn=demo_reality, frontier=Arm("frontier", GW, FrozenUpdater("big")),
                        store=store, train_run_id="t", heldout_run_id="h", frozen_in_train=True)
    s = summarise(ev)
    seg = s["segments"]["all_companies"]
    assert "frontier" in seg and seg["frontier"]["n"] == seg["n"] and s["frontier_version"].startswith("frozen:big")
    assert {c.arm for c in ev.train_cells} == {"learned", "frozen"}
    calls = store.rows("calls")
    assert len(calls) == len(ev.train_cells) + len(ev.cells)
    assert {r["run_id"] for r in calls} == {"t", "h"}
    assert len(store.rows("corrections")) == ev.corrections_applied
    snaps = snapshots(ev)
    assert {(x["phase"], x["arm"]) for x in snaps} == {("train", "learned"), ("train", "frozen"),
                                                      ("heldout", "learned"), ("heldout", "frozen"), ("heldout", "frontier")}
    assert planned_calls(SPLIT, 1, frozen_in_train=True, frontier=True)["per_agent_held_out"] == 3 * 5 * 8
    assert "frontier (no learning)" in render_markdown(build_report(SPLIT, {"fundamentals": s}, {"real_results": False}))


def test_frozen_curve_calls_never_feed_learning(tmp_path):
    a, _ = run(tmp_path / "a")
    b = evaluate_agent("fundamentals", SPLIT, GW, FakeModelUpdater(tmp_path / "b"), FrozenUpdater("m"),
                       outcome_fn=demo_reality, frozen_in_train=True)
    assert a.corrections_applied == b.corrections_applied and a.learned_version_end == b.learned_version_end
