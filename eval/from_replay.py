"""The held-out report from a finished grader.replay run: no new LLM calls, same format as eval.run.

The replay already runs the split the harness would. `grader.replay._learn` only turns a miss into a
correction when the call and its resolution both fall inside the train window and the company is not
held out, so after train_end the learned arm's lessons stop changing. Its calls in the held-out window
are a clean out-of-time test, and the held-out companies an out-of-sample one. This module scores
them exactly as eval.harness.summarise does: per segment
(all / seen / unseen companies), only (company, quarter) cells where both frozen and learned have a
resolved grade, with the naive and base-rate baselines scored on the same outcomes.

    python -m eval.run --from-replay data/runs_final --tag final
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from agents.specs import SPECS

from .baselines import score, score_baselines
from .harness import SEGMENTS
from .split import Split


def _rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def _arm(run_id: str, tag: str) -> tuple[str, str] | None:
    """'final-learned-heldout' -> ('learned', 'heldout')."""
    if not run_id.startswith(f"{tag}-"):
        return None
    arm, _, kind = run_id[len(tag) + 1:].rpartition("-")
    return (arm, kind) if arm and kind else None


def load(root: Path | str, tag: str) -> dict:
    root = Path(root)
    runs = [r for r in _rows(root / "runs.jsonl") if _arm(r["run_id"], tag)]
    if not runs:
        raise ValueError(f"{root}: no runs tagged {tag!r}")
    cfg = next((r.get("config") or {} for r in runs if (r.get("config") or {}).get("train_end")), {})
    held = set(cfg.get("held_out_companies") or [])
    for r in _rows(root / "runs.jsonl"):  # the replay also writes a top-level held-out list on one row
        held |= set((r.get("config") or {}).get("held_out_companies") or [])
    calls = {c["call_id"]: c for c in _rows(root / "calls.jsonl") if _arm(c["run_id"], tag)}
    grades = {g["call_id"]: g for g in _rows(root / "grades.jsonl") if g["call_id"] in calls}
    corrections = [c for c in _rows(root / "corrections.jsonl") if c["call_id"] in calls]
    snaps = [s for s in _rows(root / "snapshots.jsonl") if _arm(s["run_id"], tag)]
    return {"train_end": date.fromisoformat(cfg["train_end"]), "held_out": held, "calls": calls,
            "grades": grades, "corrections": corrections, "snapshots": snaps}


def _models(snaps: list[dict], agent: str, arm: str) -> list[str]:
    s = sorted((x for x in snaps if x["agent"] == agent and x["variant"] == arm), key=lambda x: x["as_of"])
    return [x["model"] for x in s if x.get("model")]


def build(root: Path | str, tag: str, agents: list[str] | None = None) -> tuple[Split, dict]:
    d = load(root, tag)
    train_end, held = d["train_end"], d["held_out"]
    cells: dict[str, dict[tuple[str, date], dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    train_outcomes, quarters, companies = defaultdict(list), set(), set()
    train_calls, train_dropped, held_dropped = defaultdict(int), defaultdict(int), defaultdict(lambda: defaultdict(int))
    for cid, c in d["calls"].items():
        arm, _ = _arm(c["run_id"], tag)
        a, q, g = c["agent"], date.fromisoformat(c["as_of"]), d["grades"].get(cid)
        quarters.add(q)
        companies.add(c["company_id"])
        resolved = g is not None and g["correct"] is not None
        if q <= train_end:
            if arm == "learned":
                train_calls[a] += 1
                train_dropped[a] += not resolved
            if arm == "frozen" and resolved and c["company_id"] not in held:
                train_outcomes[a].append(g["outcome"])  # the base-rate baseline learns from train outcomes only
            continue
        if not resolved:
            held_dropped[a][arm] += 1
            continue
        p = c["payload"]["claim"]
        cells[a][(c["company_id"], q)][arm] = {"row": (p["answer"], p["probability"], g["outcome"]),
                                               "seen": c["company_id"] not in held}

    results = {}
    for a in agents or sorted(cells):
        ctype = SPECS[a].claim_type
        segments = {}
        for seg in SEGMENTS:
            pairs = [v for v in cells[a].values() if "frozen" in v and "learned" in v
                     and not (seg == "seen_companies" and not v["frozen"]["seen"])
                     and not (seg == "unseen_companies" and v["frozen"]["seen"])]
            scored = {arm: score(ctype, [p[arm]["row"] for p in pairs]) for arm in ("frozen", "learned")}
            fr, le = scored["frozen"], scored["learned"]
            segments[seg] = {"n": len(pairs), **scored,
                             "baselines": score_baselines(ctype, [p["frozen"]["row"][2] for p in pairs], train_outcomes[a]),
                             "learned_minus_frozen": ({"accuracy": None, "brier": None} if not fr["n"] else
                                                      {"accuracy": le["accuracy"] - fr["accuracy"],
                                                       "brier": le["brier"] - fr["brier"]})}
        learned = _models(d["snapshots"], a, "learned")
        frozen = _models(d["snapshots"], a, "frozen")
        results[a] = {
            "claim_type": ctype,
            "frozen_version": frozen[-1] if frozen else None,
            "learned_version_start": learned[0] if learned else None,
            "learned_version_end": learned[-1] if learned else None,
            "frontier_version": None,
            "corrections_applied": sum(1 for c in d["corrections"] if c["agent"] == a),
            "train_calls": train_calls[a], "train_dropped": train_dropped[a],
            "train_resolved_outcomes": len(train_outcomes[a]),
            "held_out_dropped": dict(held_dropped[a]),
            "segments": segments,
        }
    qs = sorted(quarters)
    split = Split(train_companies=tuple(sorted(companies - held)), held_out_companies=tuple(sorted(held)),
                  train_quarters=tuple(q for q in qs if q <= train_end),
                  held_out_quarters=tuple(q for q in qs if q > train_end))
    return split, results
