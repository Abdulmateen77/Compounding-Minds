"""Dashboard data layer: replay cut-off, arms, correction story, scoreboard."""
from datetime import date

from dashboard import data as D


def _call(cid, agent, company, as_of, answer, prob, model, run="r1"):
    return {"call_id": cid, "run_id": run, "agent": agent, "company_id": company, "as_of": as_of,
            "payload": {"call_id": cid, "run_id": run, "agent": agent, "company_id": company, "as_of": as_of,
                        "horizon": "next_quarter",
                        "claim": {"type": "binary", "question_id": "q", "answer": answer, "probability": prob},
                        "confidence": prob, "reasoning": ["r"], "evidence": [], "principles_used": ["buffett.01"],
                        "tool_calls": 0, "model": model}}


def _grade(cid, outcome, correct, brier, resolved=None):
    return {"call_id": cid, "graded_at": "2026-10-24T00:00:00+00:00", "outcome": outcome, "correct": correct,
            "brier": brier, "evidence": [], "resolution_date": resolved}


def _bundle():
    calls = [
        _call("a1", "fundamentals", "anon_001", "2019-03-31", "yes", 0.8, "fallback/fundamentals-v0"),
        _call("a2", "fundamentals", "anon_001", "2019-06-30", "yes", 0.8, "fallback/fundamentals-v0"),
        _call("a3", "fundamentals", "anon_001", "2019-09-30", "no", 0.6, "fallback/fundamentals-v1"),
        _call("f3", "fundamentals", "anon_001", "2019-09-30", "yes", 0.8, "frozen:base+fundamentals-v0"),
        _call("r1", "risk", "anon_001", "2019-09-30", "no", 0.8, "fallback/risk-v0"),
    ]
    grades = [_grade("a1", "no", False, 0.64), _grade("a2", "yes", True, 0.04), _grade("a3", "no", True, 0.16),
              _grade("f3", "no", False, 0.64), _grade("r1", "no", True, 0.04)]
    corr = [{"correction_id": "c1", "call_id": "a1", "agent": "fundamentals", "summary": "lesson",
             "mubit_ref": "fake:fundamentals:1", "applied_at": None,
             "payload": {"as_of": "2019-03-31", "company_id": "anon_001", "error_type": "overconfident",
                         "principle_refs": ["buffett.03"]}}]
    snaps = [{"run_id": "r1", "agent": "fundamentals", "variant": "learned", "as_of": d, "n_calls": 1, "n_correct": 1, "accuracy": a,
              "brier": 0.1, "model": None} for d, a in [("2019-03-31", 0.0), ("2019-06-30", 1.0), ("2019-09-30", 1.0)]]
    raw = {"runs": [{"run_id": "r1", "kind": "train", "started_at": "x",
                     "config": {"provenance": {"real_results": False}}}],
           "calls": calls, "grades": grades, "corrections": corr, "snapshots": snaps, "eval_results": []}
    return D.build_bundle("test", raw)


def test_arm_from_model_string():
    assert D.arm_for_model("frozen:claude+risk-v0") == "frozen"
    assert D.arm_for_model("fallback/risk-v3") == "learned"
    assert D.arm_for_model("frontier:big") == "frontier"


def test_curves_stop_at_replay_date():
    c = D.accuracy_curves(_bundle(), date(2019, 6, 30), window=2)
    assert c["as_of"].max() == date(2019, 6, 30)
    assert c.iloc[-1]["rolling_accuracy"] == 0.5


def test_correction_story_skips_to_the_call_that_carries_the_update():
    s = D.correction_story(_bundle(), "c1")
    assert s["before"]["call_id"] == "a1"
    assert s["after"]["call_id"] == "a3"  # a2 was still on v0
    assert s["frozen_after"]["call_id"] == "f3"


def test_committee_uses_learned_arm_and_synthesizer_verdict():
    res = D.committee(_bundle(), "anon_001", date(2019, 9, 30), "learned")
    assert set(res["rows"]["agent"]) == {"fundamentals", "risk"}
    # fundamentals 'no' (-1 * 0.6) and risk 'no' (+1 * 0.8), equal weights -> +0.1 -> neutral
    assert res["verdict"] == "neutral"


def test_scoreboard_and_corrections_respect_as_of():
    b = _bundle()
    assert D.corrections_by_quarter(b, date(2018, 12, 31)).empty
    sb = D.scoreboard(b, date(2019, 6, 30))
    assert list(sb["agent"]) == ["fundamentals"]
    assert sb.iloc[0]["corrections"] == 1
    assert b.uses_fallback_updater()


def test_outcomes_hidden_until_resolved():
    b = _bundle()
    gc = D.graded_calls(b)
    a1 = gc[gc["call_id"] == "a1"].iloc[0]  # next_quarter call from 2019-03-31 resolves 2019-06-30
    assert a1["resolved_by"] == date(2019, 6, 30)
    assert not D.is_resolved(a1, date(2019, 3, 31))
    assert D.is_resolved(a1, date(2019, 6, 30))
    ids = set(D.just_resolved(b, date(2019, 3, 31), date(2019, 6, 30))["call_id"])
    assert ids == {"a1"}
    assert D.visible_corrections(b, date(2019, 3, 31)).empty
    assert len(D.visible_corrections(b, date(2019, 6, 30))) == 1


def test_company_table_and_search():
    b = _bundle()
    t = D.company_table(b)
    assert list(t["label"]) == ["anon_001 · unknown"]
    b.companies = D.pd.DataFrame([{"company_id": "anon_001", "sector": "Energy"}])
    t = D.company_table(b)
    assert len(D.filter_companies(t, "energy")) == 1
    assert D.filter_companies(t, "tech").empty


def test_fallback_label():
    assert D.is_fallback("fake:risk:1") and D.is_fallback(None, "fallback/risk-v1")
    assert not D.is_fallback("mubit:abc", "mubit/risk-v1")


def test_heldout_report_missing_and_bad(tmp_path):
    assert D.find_heldout_report([tmp_path / "nope.json"])[1] is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    path, rep, why = D.find_heldout_report([bad])
    assert rep is None and "bad.json" in why
    good = tmp_path / "ok.json"
    good.write_text('{"agents": {}}')
    assert D.find_heldout_report([bad, good])[1] == {"agents": {}}


def test_replay_shape_arms_provenance_and_held_out():
    from dashboard.tests.fixtures import replay_tables
    b = D.build_bundle("t", replay_tables(partial=False))
    assert D.arm_for_model("baseline:naive") == "baseline"
    assert set(b.calls["arm"]) == {"learned", "frozen", "baseline"}
    prov = b.provenance()
    assert prov["real_results"] and prov["llm"] == "mubit" and not b.uses_fallback_updater()
    assert b.held_out_companies() == {"anon_002"}
    assert b.held_out_window() is None  # train_end 2018-09-30 is after the last quarter
    # the committee and the spotlight read the learned arm only, never the baseline's calls
    res = D.committee(b, "anon_001", date(2018, 6, 30), "learned")
    assert list(res["rows"]["model"]) == ["mubit:claude-haiku-5-5+fundamentals-lessons-v1"]
    s = D.correction_story(b, "k1")
    assert s["after"]["model"].endswith("-lessons-v1") and not D.is_fallback("lessons:fundamentals:1")


def test_replay_fallback_is_flagged():
    from dashboard.tests.fixtures import replay_tables
    b = D.build_bundle("t", replay_tables(partial=False, fallback=True))
    assert b.uses_fallback_updater() and not b.provenance()["real_results"]


def test_replay_in_progress_reads_partial_files(tmp_path, monkeypatch):
    from dashboard.tests.fixtures import write_replay_run
    src = write_replay_run(tmp_path / "runs_final")
    b = D.load(str(src))  # calls.jsonl ends in a half-written line
    assert len(b.calls) == 3 * 2 * 2 + 3
    p = b.progress()
    assert p["in_progress"] and p["partial_quarters"] == [date(2018, 9, 30)]
    assert p["last_complete"] == date(2018, 6, 30) and p["quarters_complete"] == 2
    for cfg in b.runs["config"]:
        cfg["train_end"] = "2018-03-31"
    assert b.held_out_window() == (date(2018, 4, 1), date(2018, 9, 30))  # shaded on the curves
    # no companies table in a replay dir: sectors come from ingest/universe.json, ids only
    t = D.company_table(b)
    assert (t["sector"] != "unknown").all() and set(t.columns) == {"company_id", "sector", "held_out", "label"}
    assert D.source_stamp(str(src)) > 0 and D.source_stamp("postgres") == 0
    c = D.accuracy_curves(b, date(2018, 9, 30))
    assert set(c["variant"]) == {"learned", "frozen", "baseline"}


def test_resolve_source_relative_to_repo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DASHBOARD_SOURCE", "data/runs_final")
    assert D.resolve_source() == str(D.ROOT / "data" / "runs_final")
    assert D.resolve_source("postgres") == "postgres"


def test_heldout_table_reads_flat_arm_report():
    rep = {"agents": {"risk": {"arms": {"learned": {"n": 10, "accuracy": 0.8, "brier": 0.1},
                                        "frozen": {"n": 10, "accuracy": 0.7, "brier": 0.2},
                                        "baseline": {"n": 10, "accuracy": 0.6, "brier": 0.4}}}}}
    t = D.heldout_table(rep, "risk", "all_companies")
    assert list(t["arm"]) == ["frozen", "learned", "baseline: naive"]
    assert D.heldout_table(rep, "risk", "unseen_companies").empty


def test_run_live_loop_is_offline_and_fallback():
    res = D.run_live_loop("fundamentals", "anon_001", date(2019, 6, 30), date(2019, 9, 30))
    assert res["offline_demo"] and res["before"]["agent"] == "fundamentals"
    if res["update_ref"]:
        assert D.is_fallback(res["update_ref"]["ref"])
