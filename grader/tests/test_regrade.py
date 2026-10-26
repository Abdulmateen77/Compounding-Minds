"""grader.regrade: rewrites grades and snapshots for one agent, leaves the others alone."""
import json
from datetime import date

from agents.run_store import call_row, grade_row, snapshot_row
from grader.grade import grade
from grader.regrade import regrade, write
from schemas import AgentCall, Claim

Q = [date(2019, 3, 31), date(2019, 6, 30), date(2019, 9, 30), date(2019, 12, 31), date(2020, 3, 31),
     date(2020, 6, 30)]


def call(cid, agent, answer, qid):
    return AgentCall(call_id=cid, run_id="t-learned-train", agent=agent, company_id="anon_001", as_of=Q[0],
                     horizon="12_months" if agent == "risk" else "next_quarter",
                     claim=Claim(type="binary", question_id=qid, answer=answer, probability=0.8),
                     confidence=0.8, reasoning=["x"], evidence=[], tool_calls=0, model="m")


def dump(path, rows):
    path.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows))


def test_regrade_turns_unresolvable_risk_into_scored_and_rebuilds_snapshots(tmp_path):
    risk = call("r1", "risk", "no", "distress_event_12m")
    fund = call("f1", "fundamentals", "yes", "fcf_margin_improves_next_q")
    old_risk = grade(risk, lambda c: ("unresolvable", {"reason": "filing text not available"}))
    old_fund = grade(fund, lambda c: ("no", {}))
    dump(tmp_path / "calls.jsonl", [call_row(risk), call_row(fund)])
    dump(tmp_path / "grades.jsonl", [grade_row(old_risk), grade_row(old_fund)])
    dump(tmp_path / "snapshots.jsonl", [snapshot_row("t-learned-train", a, "learned", q, 0, 0, None, None, "m")
                                        for a in ("risk", "fundamentals") for q in Q])

    out = regrade(tmp_path, {"risk"}, outcome_fn=lambda c: ("no", {"resolution_date": "2020-03-31"}))
    by_id = {g["call_id"]: g for g in out["grades"]}
    assert by_id["r1"]["outcome"] == "no" and by_id["r1"]["correct"] is True
    assert by_id["f1"] == grade_row(old_fund) | {"graded_at": by_id["f1"]["graded_at"]}  # untouched
    snap = {(s["agent"], s["as_of"]): s for s in out["snapshots"]}
    assert snap[("risk", "2020-03-31")]["n_correct"] == 1 and snap[("risk", "2020-03-31")]["accuracy"] == 1.0
    assert snap[("risk", "2019-12-31")]["n_calls"] == 0
    assert out["summary"]["learned"] == {"unresolvable -> no": 1, "graded": 1, "right": 1}

    write(tmp_path, out)
    assert (tmp_path / "grades.jsonl.bak").exists()
    assert json.loads((tmp_path / "grades.jsonl").read_text().splitlines()[0])["outcome"] == "no"
