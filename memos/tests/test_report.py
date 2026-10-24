import uuid
from datetime import date, datetime, timezone

import pytest

from agents.run_store import JsonlRunStore
from agents.synthesizer import PYTHON_MODEL
from ingest.universe import load_universe
from memos.memo import DISCLAIMER
from memos.report import build_report, load_run_files, main, quarter_end
from schemas import AgentCall, Correction, Grade
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)
QIDS = {"fundamentals": ("binary", "fcf_margin_improves_next_q", "next_quarter"),
        "risk": ("binary", "distress_event_12m", "12_months"),
        "scenarios": ("bucket", "revenue_bucket_next_4q", "4_quarters")}
ANSWERS = {"fundamentals": "yes", "risk": "no", "scenarios": "bull"}
EVIDENCE = {"fundamentals": ("fcf_margin_ttm", 0.142), "risk": ("interest_coverage", 12.4),
            "scenarios": ("revenue_growth_yoy", 0.061)}


def call(agent, company, as_of, arm="learned", answer=None):
    ctype, qid, horizon = QIDS[agent]
    metric, value = EVIDENCE[agent]
    return AgentCall(call_id=str(uuid.uuid4()), run_id=f"t-{arm}-train", agent=agent, company_id=company,
                     as_of=as_of, horizon=horizon,
                     claim={"type": ctype, "question_id": qid, "answer": answer or ANSWERS[agent], "probability": 0.8},
                     confidence=0.8, reasoning=[f"{agent} sees {metric} moving the right way"],
                     evidence=[{"metric": metric, "value": value, "as_of": as_of}],
                     principles_used=[f"{agent}.01"], tool_calls=0, model=f"mubit:test+{agent}-v1")


def grade(c, outcome, resolved):
    return Grade(call_id=c.call_id, graded_at=datetime.now(timezone.utc), resolution_date=resolved,
                 outcome=outcome, correct=outcome == c.claim.answer, brier=0.04 if outcome == c.claim.answer else 0.64)


def write_runs(tmp_path, graded_now=True):
    """One replay tag 't': a learned and a frozen arm, two past quarters of history, then AS_OF."""
    store = JsonlRunStore(tmp_path)
    for arm in ("learned", "frozen"):
        store.start_run(f"t-{arm}-train", "train", {"tag": "t", "variant": arm, "train_end": "2022-12-31",
                                                     "held_out_companies": ["anon_009"]})
    # history: fundamentals always right, risk always wrong, resolved before AS_OF
    for q in (date(2018, 12, 31), date(2019, 3, 31)):
        for agent in QIDS:
            c = call(agent, "anon_001", q)
            store.write_call(c)
            store.write_grade(grade(c, c.claim.answer if agent != "risk" else "yes", date(2019, 5, 1)))
    # a risk grade resolved AFTER AS_OF: must not count in the weights
    late = call("risk", "anon_002", date(2019, 3, 31))
    store.write_call(late)
    store.write_grade(grade(late, "no", date(2019, 9, 30)))
    now = {a: call(a, "anon_007", AS_OF) for a in QIDS}
    for c in now.values():
        store.write_call(c)
    store.write_call(call("fundamentals", "anon_007", AS_OF, arm="frozen", answer="no"))
    if graded_now:
        for a, c in now.items():
            store.write_grade(grade(c, c.claim.answer if a != "risk" else "yes", date(2020, 6, 30)))
        c = now["risk"]
        store.write_correction(Correction(
            correction_id="corr-1", call_id=c.call_id, agent="risk", company_id="anon_007", as_of=AS_OF,
            predicted={"answer": "no", "probability": 0.8}, actual={"outcome": "yes", "evidence": []},
            error_type="wrong_signal", lesson="Leverage trend mattered more than coverage.",
            inputs_snapshot={"metrics": get_metrics_stub("anon_007", "risk", AS_OF)["metrics"]}),
            mubit_ref="mubit-123", applied=True)
    store.flush()
    return now


def test_quarter_end():
    assert quarter_end("2019Q2") == AS_OF and quarter_end("2020q4") == date(2020, 12, 31)
    assert quarter_end("2019-06-30") == AS_OF


def test_report_has_verdict_reasoning_metric_table_and_disclaimer(tmp_path):
    now = write_runs(tmp_path)
    rep = build_report(load_run_files(tmp_path), "anon_007", AS_OF, metrics="stub", metrics_fn=get_metrics_stub)
    md = rep.markdown
    assert md.count(DISCLAIMER) == 2 and md.rstrip().endswith(f"*{DISCLAIMER}*")
    assert rep.verdict.model == PYTHON_MODEL and rep.verdict.claim.answer == "attractive"
    for a, c in now.items():
        assert f"### {a}" in md and f"> - {c.reasoning[0]}" in md
    # weights from grades resolved by AS_OF only: risk 0 of 2 (the late grade is ignored), fundamentals 2 of 2
    assert "| risk | no | 80% | +1 | 0/2 right | 0.250 |" in md
    assert "| fundamentals | yes | 80% | +1 | 2/2 right | 0.750 |" in md
    # metric table rendered by Python from the bundle, with its source accessions
    assert "| risk | interest_coverage | 12.40x | yes | metrics engine (stub) | 0000000000-00-000001 |" in md
    assert "## Source accessions" in md and "- 0000000000-00-000001" in md
    # committee graded as a composite of the agents' actual outcomes (fundamentals yes, risk yes, scenarios bull)
    assert rep.committee_grade is not None and rep.committee_grade.outcome == "attractive"
    assert rep.committee_grade.correct is True and "Committee grade" in md and "resolved 2020-06-30" in md
    assert "Lesson recorded (Mubit ref `mubit-123`)" in md


def test_files_mode_uses_the_correction_snapshot_then_call_evidence(tmp_path):
    write_runs(tmp_path)
    md = build_report(load_run_files(tmp_path), "anon_007", AS_OF).markdown
    assert "| risk | interest_coverage | 12.40x | yes | correction snapshot | 0000000000-00-000001 |" in md
    assert "| fundamentals | fcf_margin_ttm | 14.2% | yes | call evidence | not stored in run files |" in md
    assert "--metrics postgres" in md


def test_pending_grade_and_heuristic_confidence_are_labelled(tmp_path):
    write_runs(tmp_path, graded_now=False)
    rep = build_report(load_run_files(tmp_path), "anon_007", AS_OF)
    assert rep.committee_grade is None and "pending: 0 of 3" in rep.markdown
    assert rep.calibrated_on == 0 and "uncalibrated heuristic" in rep.markdown


def test_arms_are_kept_apart(tmp_path):
    write_runs(tmp_path)
    rep = build_report(load_run_files(tmp_path), "anon_007", AS_OF, arm="frozen")
    assert "### fundamentals" in rep.markdown and "### risk" not in rep.markdown
    assert rep.verdict.claim.answer == "unattractive"
    with pytest.raises(ValueError, match="quarters with calls: 2019Q2"):
        build_report(load_run_files(tmp_path), "anon_007", date(2019, 9, 30))


def test_name_is_revealed_only_for_the_demo_company(tmp_path):
    write_runs(tmp_path)
    files = load_run_files(tmp_path)
    names = {c["company_id"]: c["name"] for c in load_universe()}
    shown = build_report(files, "anon_007", AS_OF, reveal=True, demo_company="anon_007")
    assert shown.revealed and names["anon_007"] in shown.markdown
    hidden = build_report(files, "anon_007", AS_OF, reveal=False, demo_company="anon_007")
    assert not hidden.revealed and names["anon_007"] not in hidden.markdown
    other = build_report(files, "anon_007", AS_OF, reveal=True, demo_company="anon_001")
    assert not other.revealed and names["anon_007"] not in other.markdown


def test_cli_renders_and_writes_markdown(tmp_path, capsys):
    write_runs(tmp_path / "runs")
    out = tmp_path / "report.md"
    assert main(["--runs", str(tmp_path / "runs"), "--company", "anon_007", "--quarter", "2019Q2",
                 "--out", str(out)]) == 0
    text = out.read_text()
    assert text.startswith("# Committee report: anon_007, 2019Q2") and DISCLAIMER in text
    assert "Committee report" in capsys.readouterr().out
