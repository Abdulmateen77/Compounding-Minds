"""Cost/time estimate: call counts follow the replay's rules, and --observe reads a run in progress."""
import json
import os
import time

from grader.estimate import CAP, estimate, main, observe


def test_call_counts_follow_the_replay_rules():
    e = estimate(50, 3, 28, held_out=10, repair_rate=0.0, wrong_rate=0.45)
    assert e["analyst"] == 50 * 3 * 28 * 2                      # learned + frozen; baseline is free
    assert e["reflect"] == 19 * CAP * 3                         # cap binds; quarter 1 has no grades
    few = estimate(5, 3, 28, held_out=1, repair_rate=0.0, wrong_rate=0.5)
    assert few["reflect"] == 19 * 0.5 * 4 * 3                   # held-out companies are never reflected on
    assert estimate(50, 3, 8, train_quarters=20)["reflect"] < e["reflect"]
    assert e["usd"]["claude-haiku-5-5"] < e["usd"]["claude-sonnet-5-5"] < e["usd"]["claude-opus-5-5"]
    assert estimate(50, 3, 28, workers=8)["wall_min"] < estimate(50, 3, 28, workers=1)["wall_min"]


def test_observe_reads_progress_and_live_call_rate(tmp_path):
    run = tmp_path / "runs"
    root = run / "replay_x"
    (root / "memory" / "learned").mkdir(parents=True)
    (root / "state.json").write_text(json.dumps({"tag": "x", "done_quarters": ["2018-03-31", "2018-06-30"]}))
    (run / "calls.jsonl").write_text("".join(json.dumps({"run_id": r}) + "\n" for r in ("x-learned-train", "y-a-train")))
    (run / "corrections.jsonl").write_text(json.dumps({"correction_id": "c"}) + "\n")
    (root / "memory" / "learned" / "risk.jsonl").write_text(json.dumps({"correction_id": "c"}) + "\n")
    cache = tmp_path / "llm_cache"
    cache.mkdir()
    now = time.time() + 5
    for i in range(3):
        p = cache / f"{i}.json"
        p.write_text(json.dumps({"saved_at": now + 60 * i}))
        os.utime(p, (now + 60 * i, now + 60 * i))
    o = observe(run, "x", cache)
    assert (o["quarters_done"], o["calls"], o["corrections"], o["lessons"]) == (2, 1, 1, 1)
    assert o["live_calls"] == 3 and o["minutes"] == 2.0 and o["calls_per_min"] == 1.5


def test_cli_writes_the_estimate_where_asked(tmp_path, capsys):
    out = tmp_path / "est.md"
    assert main(["--out", str(out)]) == 0
    text = out.read_text()
    assert "| claude-haiku-5-5" in text and "analyst calls: 8,820" in text
