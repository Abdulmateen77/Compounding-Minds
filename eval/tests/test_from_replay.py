"""eval.from_replay: the held-out report from a replay's stored tables, scored like eval.harness."""
import json
from datetime import date

from agents.run_store import call_row, grade_row, run_row, snapshot_row
from eval.from_replay import build
from eval.run import main
from grader.grade import grade
from schemas import AgentCall, Claim

TRAIN_Q, HELD_Q = date(2022, 9, 30), date(2023, 3, 31)


def call(cid, arm, company, q, answer):
    return AgentCall(call_id=cid, run_id=f"final-{arm}-{'train' if q <= date(2022, 12, 31) else 'heldout'}",
                     agent="fundamentals", company_id=company, as_of=q, horizon="next_quarter",
                     claim=Claim(type="binary", question_id="fcf_margin_improves_next_q", answer=answer, probability=0.7),
                     confidence=0.7, reasoning=["x"], evidence=[], tool_calls=0, model=f"m-{arm}")


def write_replay(d):
    cfg = {"tag": "final", "train_end": "2022-12-31", "held_out_companies": ["anon_002"]}
    runs = [run_row(f"final-{a}-{k}", k, cfg) for a in ("learned", "frozen") for k in ("train", "heldout")]
    # train: one frozen outcome (yes) for the base rate. held-out: seen anon_001 (learned right, frozen wrong),
    # unseen anon_002 (both right), and a learned call with no frozen twin that must not be paired.
    calls = [call("t1", "frozen", "anon_001", TRAIN_Q, "yes"),
             call("h1", "learned", "anon_001", HELD_Q, "yes"), call("h2", "frozen", "anon_001", HELD_Q, "no"),
             call("h3", "learned", "anon_002", HELD_Q, "no"), call("h4", "frozen", "anon_002", HELD_Q, "no"),
             call("h5", "learned", "anon_003", HELD_Q, "yes")]
    outcome = {"t1": "yes", "h1": "yes", "h2": "yes", "h3": "no", "h4": "no", "h5": "yes"}
    grades = [grade(c, lambda c: (outcome[c.call_id], {})) for c in calls]
    snaps = [snapshot_row("final-learned-train", "fundamentals", "learned", TRAIN_Q, 1, 1, 1.0, 0.1, "m-v0"),
             snapshot_row("final-learned-heldout", "fundamentals", "learned", HELD_Q, 1, 1, 1.0, 0.1, "m-v3")]
    for name, rows in (("runs", runs), ("calls", [call_row(c) for c in calls]),
                       ("grades", [grade_row(g) for g in grades]), ("snapshots", snaps)):
        (d / f"{name}.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in rows))


def test_segments_pair_frozen_and_learned_and_split_seen_from_unseen(tmp_path):
    write_replay(tmp_path)
    split, res = build(tmp_path, "final")
    assert split.held_out_companies == ("anon_002",) and split.held_out_quarters == (HELD_Q,)
    seg = res["fundamentals"]["segments"]
    assert seg["all_companies"]["n"] == 2                      # anon_003 has no frozen twin
    assert seg["all_companies"]["learned"]["accuracy"] == 1.0 and seg["all_companies"]["frozen"]["accuracy"] == 0.5
    assert seg["seen_companies"]["n"] == 1 and seg["unseen_companies"]["n"] == 1
    assert seg["all_companies"]["learned_minus_frozen"]["accuracy"] == 0.5
    assert seg["all_companies"]["baselines"]["base_rate"]["answer"] == "yes"   # from the train outcome only
    assert res["fundamentals"]["learned_version_start"] == "m-v0" and res["fundamentals"]["learned_version_end"] == "m-v3"


def test_eval_run_from_replay_writes_the_official_report_shape(tmp_path):
    write_replay(tmp_path)
    out = tmp_path / "reports"
    assert main(["--from-replay", str(tmp_path), "--tag", "final", "--agents", "fundamentals", "--out", str(out)]) == 0
    rep = json.loads((out / "heldout_report.json").read_text())
    assert rep["banner"] is None and rep["provenance"]["real_results"] is True
    assert set(rep["agents"]["fundamentals"]["segments"]) == {"all_companies", "seen_companies", "unseen_companies"}
    assert (out / "heldout_report.md").exists()
