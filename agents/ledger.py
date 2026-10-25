"""Local count of the calls Mubit keeps, per task per UTC day.

Mubit has no API to read a task's example count, so we keep our own. A task is the system prompt
plus the model, so rows are keyed by (model, system_sha). Calls sent with record=False are logged
but not counted. Retries inside the Anthropic SDK are invisible here; the truncation loop's extra
calls are counted.

    python -m agents.ledger            # table of recorded calls per task per day, with warnings
"""
from __future__ import annotations

import json
import os
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .gateway import MubitRequest

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "mubit_ledger.jsonl"  # data/ is gitignored
FIRST_TRAINING_EXAMPLES = 25   # Mubit: a task first trains at 25 kept examples (docs.mubit.ai)
DAILY_REVIEW_CAP = 200         # new calls Mubit reviews per task per day; from the team's brief, not checked in the docs

_lock = threading.Lock()


class CallLedger:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or os.environ.get("MUBIT_LEDGER") or DEFAULT_PATH)

    def add(self, req: MubitRequest) -> None:
        row = {"day": datetime.now(timezone.utc).date().isoformat(), "agent": req.agent, "purpose": req.purpose,
               "model": req.model, "system_sha": req.system_sha, "recorded": req.recorded,
               "request_id": req.request_id}
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def recorded_per_task_day(self) -> Counter:
        """(model, system_sha, day) -> recorded calls that day."""
        return Counter((r["model"], r["system_sha"], r["day"]) for r in self.rows() if r["recorded"])

    def recorded_per_task(self) -> Counter:
        """(model, system_sha) -> recorded calls in total (an upper bound on kept examples)."""
        c: Counter = Counter()
        for (model, sha, _day), n in self.recorded_per_task_day().items():
            c[(model, sha)] += n
        return c


def report(ledger: CallLedger) -> list[str]:
    rows = ledger.rows()
    names: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        names.setdefault((r["model"], r["system_sha"]), set()).add(r["agent"])
    out = [f"{'task (model, system_sha)':<46} {'agents':<28} {'day':<11} {'sent':>5} {'total':>6}  note"]
    totals, per_day = ledger.recorded_per_task(), ledger.recorded_per_task_day()
    for (model, sha, day), n in sorted(per_day.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2])):
        total = totals[(model, sha)]
        note = []
        if total < FIRST_TRAINING_EXAMPLES:
            note.append(f"{FIRST_TRAINING_EXAMPLES - total} more until first training")
        if n > DAILY_REVIEW_CAP:
            note.append(f"over the {DAILY_REVIEW_CAP}/day review cap by {n - DAILY_REVIEW_CAP}")
        out.append(f"{model + ' ' + str(sha):<46} {','.join(sorted(names[(model, sha)]))[:27]:<28} {day:<11} "
                   f"{n:>5} {total:>6}  {'; '.join(note)}")
    unrecorded = sum(not r["recorded"] for r in rows)
    out.append(f"unrecorded calls (record=False, not counted): {unrecorded}")
    return out


def main() -> int:
    ledger = CallLedger()
    if not ledger.rows():
        print(f"no calls logged yet ({ledger.path})")
        return 0
    print("\n".join(report(ledger)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
