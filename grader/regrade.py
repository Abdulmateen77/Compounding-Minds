"""Re-grade stored calls in a JSON-lines run directory with the current rules. No LLM, no live calls.

Why: until the fix in grader/risk.py the going-concern check looked for filing text under data/filings/,
which never existed (ingest caches it under data/raw/sec/...), so almost every Risk call came back
`unresolvable` and only "yes" outcomes were ever scored. The calls themselves are fine; only the grades
and the per-quarter snapshots built from them are wrong. This rewrites both for the chosen agents.

    python -m grader.regrade --runs data/runs_final                 # Risk only, prints the change
    python -m grader.regrade --runs data/runs_final --write         # rewrites grades/snapshots (.bak kept)

Run it only when no replay is writing to that directory (the replay rewrites the files each quarter).
Sapling is replay-only by default: a keyword hit with no saved verdict stays `unresolvable` (--sapling-live
allows the call). Corrections are left as they are: the "yes" grades they came from do not change.
"""
from __future__ import annotations

import argparse
import bisect
import json
import shutil
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from grader import rules
from grader.grade import grade
from grader.replay import resolve_by
from grader.sapling import SaplingClient
from schemas import AgentCall

from agents.run_store import grade_row


def _rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def regrade(run_dir: Path, agents: set[str], outcome_fn=rules.rules_outcome) -> dict:
    """Return the new grade and snapshot rows plus a before/after summary. Writes nothing."""
    calls = {r["call_id"]: r for r in _rows(run_dir / "calls.jsonl")}
    grades = _rows(run_dir / "grades.jsonl")
    snaps = _rows(run_dir / "snapshots.jsonl")
    quarters = sorted({date.fromisoformat(s["as_of"]) for s in snaps})
    if not quarters:
        raise ValueError(f"{run_dir}: no snapshots, so the replay quarters are unknown")

    new_grades, placed = [], defaultdict(list)          # placed[(run_id, agent, quarter)] -> [grade row]
    summary = defaultdict(lambda: defaultdict(int))
    for row in grades:
        c = calls.get(row["call_id"])
        if c is None or c["agent"] not in agents:
            new_grades.append(row)
            continue
        call = AgentCall(**c["payload"])
        g = grade(call, outcome_fn)
        due = resolve_by(call, g)
        i = bisect.bisect_left(quarters, due)            # the replay grades in the first quarter >= due
        arm = c["run_id"].rsplit("-", 2)[-2] if c["run_id"].count("-") >= 2 else c["run_id"]
        summary[arm][f"{row['outcome']} -> {g.outcome}"] += 1
        if i == len(quarters):                           # not visible within the replay: it stays pending
            summary[arm]["dropped (resolves after the last quarter)"] += 1
            continue
        new = grade_row(g)
        new_grades.append(new)
        placed[(c["run_id"], c["agent"], quarters[i])].append(new)
        if g.correct is not None:
            summary[arm]["graded"] += 1
            summary[arm]["right"] += bool(g.correct)

    new_snaps = []
    for s in snaps:
        if s["agent"] not in agents:
            new_snaps.append(s)
            continue
        gs = [g for g in placed.get((s["run_id"], s["agent"], date.fromisoformat(s["as_of"])), [])
              if g["correct"] is not None]
        n, k = len(gs), sum(bool(g["correct"]) for g in gs)
        new_snaps.append({**s, "n_calls": n, "n_correct": k, "accuracy": k / n if n else None,
                          "brier": sum(g["brier"] for g in gs) / n if n else None})

    return {"grades": new_grades, "snapshots": new_snaps, "summary": {a: dict(r) for a, r in summary.items()}}


def write(run_dir: Path, result: dict) -> None:
    for table in ("grades", "snapshots"):
        p = run_dir / f"{table}.jsonl"
        if p.exists():
            shutil.copy2(p, p.with_suffix(".jsonl.bak"))
        tmp = p.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(r, default=str) + "\n" for r in result[table]))
        tmp.replace(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", required=True, help="a JSON-lines run directory (e.g. data/runs_final)")
    ap.add_argument("--agents", default="risk", help="comma list of agents to re-grade (default risk)")
    ap.add_argument("--write", action="store_true", help="rewrite grades.jsonl and snapshots.jsonl (keeps .bak)")
    ap.add_argument("--sapling-live", action="store_true", help="allow live Sapling calls for unsaved verdicts")
    a = ap.parse_args(argv)

    from store import queries
    queries.use_postgres()
    rules.set_sapling(SaplingClient(replay_only=not a.sapling_live))
    run_dir = Path(a.runs)
    result = regrade(run_dir, set(a.agents.split(",")))
    print(json.dumps(result["summary"], indent=2))
    if a.write:
        write(run_dir, result)
        print(f"rewrote {run_dir}/grades.jsonl and snapshots.jsonl (originals in *.jsonl.bak)")
    else:
        print("dry run: nothing written (pass --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
