"""Reading scored calls from a replay's JSONL directory (no database)."""
from __future__ import annotations

import json

from quality.load import load_scored_dir
from quality.tests.helpers import make_call


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_jsonl_dir_gives_the_variant_and_the_last_written_grade(tmp_path):
    learned, frozen = make_call(), make_call()
    _write(tmp_path / "runs.jsonl", [{"run_id": "t-learned-train", "config": {"variant": "learned"}},
                                     {"run_id": "t-frozen-train", "config": {"variant": "frozen"}}])
    _write(tmp_path / "calls.jsonl", [
        {"call_id": learned.call_id, "run_id": "t-learned-train", "payload": learned.model_dump(mode="json")},
        {"call_id": frozen.call_id, "run_id": "t-frozen-train", "payload": frozen.model_dump(mode="json")}])
    grade = lambda cid, outcome, correct: {"call_id": cid, "graded_at": "2025-01-01T00:00:00+00:00",  # noqa: E731
                                          "outcome": outcome, "correct": correct, "brier": None,
                                          "evidence": [{"resolution_date": "2019-11-01"}]}
    _write(tmp_path / "grades.jsonl", [grade(learned.call_id, "unresolvable", None),
                                       grade(learned.call_id, "yes", True),       # a regrade, written later
                                       grade(frozen.call_id, "no", False)])
    got = {s.variant: s for s in load_scored_dir(tmp_path)}
    assert set(got) == {"learned", "frozen"}
    assert got["learned"].grade.outcome == "yes" and got["learned"].grade.correct is True
    assert str(got["frozen"].grade.resolution_date) == "2019-11-01"
    assert load_scored_dir(tmp_path, ["t-frozen-train"])[0].variant == "frozen"
