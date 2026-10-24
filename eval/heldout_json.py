"""Write eval/out/heldout.json (handoff 9) from a finished replay's stored tables.

    python -m eval.heldout_json data/runs_final final

Reads calls, grades and runs (JSONL) for the tag, keeps the `heldout` runs, and reports per agent and
arm (learned, frozen, baseline): graded calls, accuracy and mean Brier, plus learned minus frozen.
Only resolved calls have a grade, so unresolvable ones are excluded, as in the report.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out" / "heldout.json"
ARMS = ("learned", "frozen", "baseline")


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build(root: Path, tag: str) -> dict:
    runs = {r["run_id"]: r for r in _rows(root / "runs.jsonl")}
    arm_of = {rid: rid[len(tag) + 1:].rsplit("-", 1)[0] for rid in runs if rid.startswith(f"{tag}-")}
    kind_of = {rid: rid.rsplit("-", 1)[1] for rid in arm_of}
    calls = {c["call_id"]: c for c in _rows(root / "calls.jsonl") if kind_of.get(c["run_id"]) == "heldout"}
    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for g in _rows(root / "grades.jsonl"):
        c = calls.get(g["call_id"])
        if c:
            cells[(c["agent"], arm_of[c["run_id"]])].append(g)

    def stat(gs: list[dict]) -> dict:
        n = len(gs)
        return {"n": n, "accuracy": sum(g["correct"] for g in gs) / n if n else None,
                "brier": sum(g["brier"] for g in gs) / n if n else None}

    agents: dict[str, dict] = {}
    for agent in sorted({a for a, _ in cells}):
        arms = {arm: stat(cells[(agent, arm)]) for arm in ARMS if (agent, arm) in cells}
        entry: dict = {"arms": arms}
        le, fr = arms.get("learned"), arms.get("frozen")
        if le and fr and le["n"] and fr["n"]:
            entry["learned_minus_frozen"] = {"accuracy": le["accuracy"] - fr["accuracy"],
                                             "brier": le["brier"] - fr["brier"]}
        agents[agent] = entry
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tag": tag,
            "source": str(root), "disclaimer": "Research tool, not financial advice.", "agents": agents}


def main(argv: list[str]) -> int:
    root, tag = Path(argv[0]), argv[1]
    report = build(root, tag)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
