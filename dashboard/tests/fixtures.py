"""Stored-run fixtures for the dashboard and API tests.

    demo_runs_dir()          data/runs if it exists, else the same offline preview generated once into a
                             temp dir (python -m eval.run ... --curves --save), so a fresh checkout passes
    write_replay_run(dir)    a small table set in grader.replay's shape (learned/frozen/baseline arms,
                             top-level held-out list, 'lessons:' refs), optionally still being written
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def demo_runs_dir() -> Path:
    stored = ROOT / "data" / "runs"
    if (stored / "calls.jsonl").exists():
        return stored
    from eval.run import main  # offline: scripted LLM, stub metrics, fallback updater, no network
    out = Path(tempfile.mkdtemp(prefix="cm-demo-runs-"))
    with contextlib.redirect_stdout(io.StringIO()):
        main(["--agents", "fundamentals,risk,scenarios", "--curves", "--save", str(out / "runs"),
              "--out", str(out / "report")])
    return out / "runs"


def _call(cid, run, agent, company, as_of, answer, prob, model):
    return {"call_id": cid, "run_id": run, "agent": agent, "company_id": company, "as_of": as_of,
            "payload": {"call_id": cid, "run_id": run, "agent": agent, "company_id": company, "as_of": as_of,
                        "horizon": "next_quarter",
                        "claim": {"type": "binary", "question_id": "fcf_margin_improves_next_q",
                                  "answer": answer, "probability": prob},
                        "confidence": prob, "reasoning": ["fcf_slope_8q is positive."],
                        "evidence": [{"metric": "fcf_slope_8q", "value": 0.03, "as_of": as_of}],
                        "principles_used": ["buffett.01"], "tool_calls": 0, "model": model}}


def replay_tables(partial: bool = True, fallback: bool = False) -> dict[str, list[dict]]:
    """Two companies, fundamentals, three arms. Q1 and Q2 are complete; with `partial`, Q3 has
    calls for one company only and no snapshot yet (the replay is mid-quarter)."""
    held = ["anon_002"]
    learned = (lambda v: f"fallback/fundamentals-v{v}") if fallback else \
        (lambda v: f"mubit:claude-haiku-5-5+fundamentals-lessons-v{v}")
    arms = {"learned": learned, "frozen": lambda v: "frozen:claude-haiku-5-5+fundamentals-v0",
            "baseline": lambda v: "baseline:naive"}
    runs = [{"run_id": f"t-{a}-train", "kind": "train", "started_at": f"2026-10-24T18:00:0{i}+00:00",
             "config": {"tag": "t", "variant": a, "companies": 2, "agents": ["fundamentals"],
                        "held_out_companies": held, "train_end": "2018-09-30",
                        "updater_fallback": fallback and a == "learned"}}
            for i, a in enumerate(arms)]
    quarters = ["2018-03-31", "2018-06-30"] + (["2018-09-30"] if partial else [])
    calls, grades, snaps = [], [], []
    for qi, q in enumerate(quarters):
        for a, model in arms.items():
            for co in ("anon_001", "anon_002"):
                if partial and qi == 2 and co == "anon_002":
                    continue  # not written yet
                cid = f"{a}-{co}-{q}"
                ans = "yes" if a == "baseline" else ("no" if qi == 0 else "yes")
                calls.append(_call(cid, f"t-{a}-train", "fundamentals", co, q, ans, 0.7,
                                   model(1 if qi >= 1 and a == "learned" else 0)))
                if qi < 2:  # graded in the following quarter; Q3 is not graded yet
                    right = ans == "yes"
                    grades.append({"call_id": cid, "graded_at": "2026-10-24T18:10:00+00:00",
                                   "outcome": "yes", "correct": right, "brier": 0.09 if right else 0.49,
                                   "evidence": [{"rule": "fcf_margin_improves_next_q"}],
                                   "resolution_date": "2018-05-01" if qi == 0 else "2018-08-01"})
        if qi < 2:
            for a, model in arms.items():
                snaps.append({"run_id": f"t-{a}-train", "agent": "fundamentals", "variant": a, "as_of": q,
                              "n_calls": 0 if qi == 0 else 2, "n_correct": 0 if qi == 0 else 1,
                              "accuracy": None if qi == 0 else 0.5, "brier": None if qi == 0 else 0.3,
                              "model": model(0)})
    ref = "fake:fundamentals:1" if fallback else "lessons:fundamentals:1"
    corrections = [{"correction_id": "k1", "call_id": "learned-anon_001-2018-03-31", "agent": "fundamentals",
                    "summary": "Do not forecast a reversal from one quarter.", "mubit_ref": ref,
                    "applied_at": "2026-10-24T18:10:28+00:00",
                    "payload": {"correction_id": "k1", "call_id": "learned-anon_001-2018-03-31",
                                "agent": "fundamentals", "company_id": "anon_001", "as_of": "2018-03-31",
                                "predicted": {"answer": "no", "probability": 0.7},
                                "actual": {"outcome": "yes", "evidence": []}, "error_type": "wrong_signal",
                                "lesson": "Do not forecast a reversal from one quarter.",
                                "principle_refs": ["buffett.04"], "inputs_snapshot": {"metrics": []}}}]
    return {"runs": runs, "calls": calls, "grades": grades, "corrections": corrections, "snapshots": snaps}


def write_replay_run(directory: Path, partial: bool = True, fallback: bool = False) -> Path:
    """Write replay_tables() as JSONL. With `partial`, calls.jsonl ends in a half-written line."""
    directory.mkdir(parents=True, exist_ok=True)
    for table, rows in replay_tables(partial, fallback).items():
        text = "".join(json.dumps(r) + "\n" for r in rows)
        if partial and table == "calls":
            text += json.dumps(rows[0])[:57]  # the writer was interrupted mid-line
        (directory / f"{table}.jsonl").write_text(text)
    return directory
