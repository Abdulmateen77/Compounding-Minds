"""heldout.json (the dashboard's contract) and quality.md."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from quality import report
from quality.metrics import Scored
from quality.report import build_heldout, build_quality, critique, write_reports
from quality.tests.helpers import make_scored

HELD = {"anon_090", "anon_091"}
NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)
SLICE_KEYS = {"n", "learned", "frozen", "always_yes", "base_rate"}


def twin(outcome, learned_answer, frozen_answer, company="anon_090", as_of=date(2023, 6, 30), prob=0.7,
         agent="fundamentals", **kw) -> list[Scored]:
    """The same case seen by both variants."""
    return [make_scored(outcome, variant="learned", agent=agent, company=company, as_of=as_of, answer=learned_answer, prob=prob, **kw),
            make_scored(outcome, variant="frozen", agent=agent, company=company, as_of=as_of, answer=frozen_answer, prob=prob, **kw)]


def training(n_yes, n_no, agent="fundamentals"):
    out = []
    for i in range(n_yes + n_no):
        out += twin("yes" if i < n_yes else "no", "yes", "yes", company=f"anon_{i + 1:03d}", as_of=date(2019, 6, 30), agent=agent)
    return out


def heldout_cases(learned_right: bool, frozen_right: bool, n=4, agent="fundamentals") -> list[Scored]:
    out = []
    for i in range(n):
        # outcome is always yes: right means answering yes
        out += twin("yes", "yes" if learned_right else "no", "yes" if frozen_right else "no",
                    company="anon_090", as_of=date(2023, 3, 31 + 0) if i == 0 else date(2023 + (i > 1), (3, 6, 9, 12)[i], (31, 30, 30, 31)[i]),
                    agent=agent)
    return out


def notes_about(h, text):
    return [n for n in h["notes"] if text in n]


# ---- the contract --------------------------------------------------------------------------------------

def test_heldout_json_has_exactly_the_documented_keys():
    h = build_heldout(training(3, 1) + heldout_cases(True, False), HELD, now=NOW)
    assert set(h) == {"generated_at", "split", "agents", "notes"}
    assert set(h["split"]) == {"train_years", "heldout_years", "heldout_company_ids"}
    assert h["split"]["train_years"] == [2018, 2022] and h["split"]["heldout_years"] == [2023, 2024]
    assert h["split"]["heldout_company_ids"] == sorted(HELD)
    assert h["generated_at"] == NOW.isoformat()
    block = h["agents"]["fundamentals"]
    assert set(block) == {"slices", "unresolvable"}
    assert set(block["slices"]) == {"unseen_years", "unseen_companies", "unseen_both"}
    for s in block["slices"].values():
        assert set(s) == SLICE_KEYS
        for who in ("learned", "frozen", "always_yes", "base_rate"):
            assert set(s[who]) == {"accuracy", "brier"}


def test_the_written_file_is_valid_json_with_no_nan(tmp_path):
    scored = training(3, 1) + heldout_cases(True, False)
    heldout, path, _ = write_reports(tmp_path, scored, HELD, now=NOW)
    text = path.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    assert json.loads(text, parse_constant=lambda c: pytest.fail(f"bare {c} in the file")) == heldout


def test_a_corrupt_nan_grade_fails_loudly_and_writes_no_file(tmp_path):
    """The metric functions return None for 'nothing to measure', so NaN can only come from a broken
    grade. The writer must refuse it rather than hand the dashboard a file it cannot parse."""
    nan = float("nan")
    broken = [s.__class__(call=s.call, grade=s.grade.model_copy(update={"brier": nan}), variant=s.variant)
              for s in heldout_cases(True, True)]
    with pytest.raises(ValueError, match="Out of range float values"):
        write_reports(tmp_path, training(3, 1) + broken, HELD, now=NOW)
    assert not (tmp_path / "heldout.json").exists() and not (tmp_path / "quality.md").exists()


def test_a_slice_with_no_calls_is_n_zero_with_nulls_not_nan():
    h = build_heldout(training(3, 1), HELD, now=NOW)       # training data only: every held-out slice is empty
    for name in ("unseen_years", "unseen_companies", "unseen_both"):
        s = h["agents"]["fundamentals"]["slices"][name]
        assert s["n"] == 0
        for who in ("learned", "frozen", "always_yes", "base_rate"):
            assert s[who] == {"accuracy": None, "brier": None}
    assert notes_about(h, "no comparable calls in fundamentals/unseen_years")
    assert not notes_about(h, "learned does not beat frozen")      # nothing to compare is not a loss


def test_no_data_at_all_still_writes_both_files(tmp_path):
    h, hp, qp = write_reports(tmp_path / "deep" / "out", [], HELD, now=NOW)
    assert h["agents"] == {} and hp.exists() and qp.exists()
    assert "nothing to report" in qp.read_text(encoding="utf-8")


# ---- the numbers ---------------------------------------------------------------------------------------

def test_learned_and_frozen_are_scored_on_the_same_cases_with_hand_numbers():
    # one held-out company, one held-out year, four cases, outcome always yes. Both variants answer yes at 0.7
    # -> right, brier (0.7-1)^2 = 0.09. Frozen answers no at 0.7 -> wrong, p(yes) = 0.3, brier 0.49.
    h = build_heldout(training(3, 1) + heldout_cases(True, False), HELD, now=NOW)
    s = h["agents"]["fundamentals"]["slices"]["unseen_both"]
    assert s["n"] == 4
    assert s["learned"] == {"accuracy": 1.0, "brier": 0.09}
    assert s["frozen"] == {"accuracy": 0.0, "brier": 0.49}
    assert s["always_yes"] == {"accuracy": 1.0, "brier": 0.0}      # the outcome is always yes
    assert s["base_rate"] == {"accuracy": 1.0, "brier": 0.0625}    # training was 3 yes of 4 -> p(yes) = 0.75


def test_only_the_right_slices_receive_a_call():
    scored = (training(3, 1)
              + twin("yes", "yes", "yes", company="anon_001", as_of=date(2023, 3, 31))     # unseen_years
              + twin("yes", "yes", "yes", company="anon_090", as_of=date(2021, 3, 31))     # unseen_companies only
              + twin("yes", "yes", "yes", company="anon_091", as_of=date(2024, 3, 31)))    # companies + both
    s = build_heldout(scored, HELD, now=NOW)["agents"]["fundamentals"]["slices"]
    assert (s["unseen_years"]["n"], s["unseen_companies"]["n"], s["unseen_both"]["n"]) == (1, 2, 1)


def test_unresolvable_cases_are_counted_and_left_out_of_every_score():
    scored = training(3, 1) + heldout_cases(True, False) + twin("unresolvable", "yes", "yes", company="anon_091", as_of=date(2024, 3, 31))
    block = build_heldout(scored, HELD, now=NOW)["agents"]["fundamentals"]
    assert block["unresolvable"] == 1                              # one case, not one per variant
    assert block["slices"]["unseen_both"]["n"] == 4                # unchanged by the unresolvable case


def test_a_case_resolved_by_only_one_variant_is_left_out_of_both_and_reported():
    learned_only = make_scored("yes", variant="learned", company="anon_090", as_of=date(2023, 3, 31), answer="yes")
    frozen_dropped = make_scored("unresolvable", variant="frozen", company="anon_090", as_of=date(2023, 3, 31), answer="yes")
    h = build_heldout(training(3, 1) + [learned_only, frozen_dropped], HELD, now=NOW)
    assert h["agents"]["fundamentals"]["slices"]["unseen_both"]["n"] == 0
    assert notes_about(h, "from only one of learned and frozen")


def test_the_same_case_in_two_runs_is_counted_once_keeping_the_latest():
    early = datetime(2025, 1, 1, tzinfo=timezone.utc)
    late = datetime(2025, 2, 1, tzinfo=timezone.utc)
    old = make_scored("yes", variant="learned", company="anon_090", as_of=date(2023, 3, 31), answer="no", graded_at=early)
    new = make_scored("yes", variant="learned", company="anon_090", as_of=date(2023, 3, 31), answer="yes", graded_at=late)
    frozen = make_scored("yes", variant="frozen", company="anon_090", as_of=date(2023, 3, 31), answer="yes")
    h = build_heldout(training(3, 1) + [old, new, frozen], HELD, now=NOW)
    s = h["agents"]["fundamentals"]["slices"]["unseen_both"]
    assert s["n"] == 1 and s["learned"]["accuracy"] == 1.0         # the later record, not an average of both
    assert notes_about(h, "appeared in more than one run")


def test_other_variants_are_ignored_and_reported():
    odd = make_scored("yes", variant="baseline", company="anon_090", as_of=date(2023, 3, 31))
    h = build_heldout(training(3, 1) + heldout_cases(True, True) + [odd], HELD, now=NOW)
    assert notes_about(h, "ignored 1 records with variant 'baseline'")
    assert h["agents"]["fundamentals"]["slices"]["unseen_both"]["n"] == 4


def test_a_missing_variant_gives_a_null_column_and_a_note():
    learned_only = [s for s in training(3, 1) + heldout_cases(True, True) if s.variant == "learned"]
    h = build_heldout(learned_only, HELD, now=NOW)
    s = h["agents"]["fundamentals"]["slices"]["unseen_both"]
    assert s["frozen"] == {"accuracy": None, "brier": None} and s["learned"]["accuracy"] == 1.0
    assert notes_about(h, "no frozen records for fundamentals")
    assert not notes_about(h, "learned does not beat frozen")      # there is no frozen to lose to


# ---- "learned does not beat frozen" --------------------------------------------------------------------

def test_the_note_appears_when_learned_is_worse():
    h = build_heldout(training(3, 1) + heldout_cases(learned_right=False, frozen_right=True), HELD, now=NOW)
    notes = notes_about(h, "learned does not beat frozen on fundamentals/unseen_both")
    assert len(notes) == 1 and "is worse" in notes[0]
    assert "0.4900 vs 0.0900" in notes[0]                          # the numbers behind it are in the note


def test_the_note_appears_when_learned_only_matches_frozen():
    h = build_heldout(training(3, 1) + heldout_cases(True, True), HELD, now=NOW)
    notes = notes_about(h, "learned does not beat frozen on fundamentals/unseen_both")
    assert len(notes) == 1 and "matched it" in notes[0]


def test_the_note_is_absent_when_learned_beats_frozen():
    h = build_heldout(training(3, 1) + heldout_cases(learned_right=True, frozen_right=False), HELD, now=NOW)
    assert not notes_about(h, "learned does not beat frozen")


def test_a_win_on_one_slice_does_not_hide_a_loss_on_another():
    """unseen_years: a training company in 2023, learned right and frozen wrong -> a win.
    unseen_both: a held-out company in 2023, learned wrong and frozen right -> a loss. The cases
    are different, so one slice cannot offset the other."""
    scored = (training(3, 1)
              + twin("yes", "yes", "no", company="anon_001", as_of=date(2023, 3, 31))     # unseen_years
              + twin("yes", "no", "yes", company="anon_090", as_of=date(2023, 3, 31)))    # unseen_both
    h = build_heldout(scored, HELD, now=NOW)
    slices = h["agents"]["fundamentals"]["slices"]
    assert slices["unseen_years"]["learned"]["brier"] < slices["unseen_years"]["frozen"]["brier"]
    assert slices["unseen_both"]["learned"]["brier"] > slices["unseen_both"]["frozen"]["brier"]
    assert not notes_about(h, "does not beat frozen on fundamentals/unseen_years")   # the win is not flagged
    assert notes_about(h, "does not beat frozen on fundamentals/unseen_both")        # the loss is


def test_each_agent_gets_its_own_notes():
    scored = (training(3, 1) + heldout_cases(False, True)
              + training(2, 2, agent="risk") + heldout_cases(True, False, agent="risk"))
    h = build_heldout(scored, HELD, now=NOW)
    assert notes_about(h, "does not beat frozen on fundamentals/unseen_both")
    assert not notes_about(h, "does not beat frozen on risk/")


# ---- quality.md ------------------------------------------------------------------------------------------

def test_quality_has_one_section_per_agent_and_the_disclaimer():
    scored = training(3, 1) + heldout_cases(True, False) + training(2, 2, agent="risk") + heldout_cases(True, True, agent="risk")
    text = build_quality(scored, HELD, now=NOW)
    assert text.count("\n## ") == 2 and "## fundamentals" in text and "## risk" in text
    assert text.count("Research tool, not financial advice.") == 2          # top and bottom
    assert "**Critique (learned).**" in text
    for row in ("Valid-JSON rate", "Evidence match", "Accuracy", "Brier", "Overconfidence gap", "Calibration, learned"):
        assert row in text


def test_quality_says_na_rather_than_guessing_what_it_cannot_know():
    text = build_quality(training(3, 1) + heldout_cases(True, True), HELD, now=NOW)
    row = next(l for l in text.splitlines() if l.startswith("| Valid-JSON rate"))
    assert "n/a" in row                                                    # attempts were not supplied
    assert "n/a" in next(l for l in text.splitlines() if l.startswith("| Evidence match"))


def test_quality_uses_attempts_and_bundles_when_given():
    scored = training(3, 1) + heldout_cases(True, True)
    produced = len([s for s in scored if s.variant == "learned"])
    text = build_quality(scored, HELD, attempted={"fundamentals": produced * 2}, bundles={}, now=NOW)
    assert "| Valid-JSON rate | 50% |" in text.replace("  ", " ")


def test_quality_notes_are_listed_when_there_are_any():
    text = build_quality(training(3, 1), HELD, now=NOW, extra_notes=["SYNTHETIC DEMO DATA"])
    assert "Notes:" in text and "- SYNTHETIC DEMO DATA" in text


# ---- the rule-written critique ----------------------------------------------------------------------------

def stats(**over):
    base = {"resolved": 100, "accuracy": 0.7, "brier": 0.2, "mean_confidence": 0.7, "gap": 0.0,
            "valid_json_rate": 1.0, "evidence_match": 1.0, "bins": []}
    return {**base, **over}


def test_a_gap_above_ten_points_reads_as_overconfident():
    text = critique(stats(gap=0.15, mean_confidence=0.85), baseline_acc=0.5, baseline_brier=0.3)
    assert "overconfident" in text and "85%" in text and "70%" in text


def test_a_gap_at_exactly_the_threshold_is_not_called_overconfident():
    assert "overconfident" not in critique(stats(gap=0.10), baseline_acc=0.5, baseline_brier=0.3)


def test_a_large_negative_gap_reads_as_underconfident():
    assert "underconfident" in critique(stats(gap=-0.2, mean_confidence=0.5), 0.5, 0.3)


def test_not_beating_the_base_rate_is_named():
    text = critique(stats(brier=0.25), baseline_acc=0.6, baseline_brier=0.20)
    assert "no better than the base-rate baseline" in text and "0.250" in text and "0.200" in text


def test_a_small_sample_always_leads():
    text = critique(stats(resolved=7, gap=0.3), baseline_acc=0.5, baseline_brier=0.3)
    assert text.startswith("Only 7 resolved calls")


def test_at_most_two_sentences_even_when_everything_is_wrong():
    text = critique(stats(resolved=5, gap=0.3, brier=0.4, valid_json_rate=0.8, evidence_match=0.5), 0.9, 0.1)
    assert text.count(". ") + text.count(".") <= 4 and len([s for s in text.split(". ") if s]) <= 3


def test_a_weak_confidence_bin_is_named_when_there_is_no_overall_gap():
    bins = [{"lo": 0.8, "hi": 1.0, "n": 12, "mean_confidence": 0.9, "accuracy": 0.55}]
    text = critique(stats(bins=bins), baseline_acc=0.5, baseline_brier=0.3)
    assert "80% to 100% confident it was right only 55%" in text


def test_a_thin_bin_is_not_scolded():
    bins = [{"lo": 0.8, "hi": 1.0, "n": 2, "mean_confidence": 0.9, "accuracy": 0.0}]
    assert "80% to 100%" not in critique(stats(bins=bins), baseline_acc=0.5, baseline_brier=0.3)


def test_invalid_replies_and_evidence_mismatches_are_named():
    text = critique(stats(valid_json_rate=0.8), baseline_acc=0.5, baseline_brier=0.3)
    assert "invalid reply on 20%" in text
    assert "evidence did not match" in critique(stats(evidence_match=0.9), 0.5, 0.3)


def test_a_healthy_agent_gets_no_clear_weakness_and_no_boasting():
    text = critique(stats(), baseline_acc=0.5, baseline_brier=0.3)
    assert text.startswith("No clear weakness") and "not proof" in text


def test_no_resolved_calls_says_so():
    assert critique(stats(resolved=0), 0.5, 0.3) == "No resolved calls yet, so there is nothing to assess."


def test_the_critique_never_uses_advice_language():
    texts = [critique(stats(gap=0.2), 0.5, 0.3), critique(stats(), 0.5, 0.3), critique(stats(resolved=3), 0.9, 0.1)]
    for t in texts:
        for word in ("buy", "sell", "target price", "recommend", "outperform"):
            assert word not in t.lower()


# ---- the demo and the CLI ---------------------------------------------------------------------------------

def test_demo_writes_both_files_labels_itself_and_exercises_win_tie_and_loss(tmp_path, capsys):
    from quality.cli import main

    assert main(["--demo", "--out", str(tmp_path)]) == 0
    heldout = json.loads((tmp_path / "heldout.json").read_text(encoding="utf-8"))
    quality = (tmp_path / "quality.md").read_text(encoding="utf-8")
    assert any("SYNTHETIC DEMO DATA" in n for n in heldout["notes"]) and "SYNTHETIC DEMO DATA" in quality
    assert set(heldout["agents"]) == {"fundamentals", "risk", "scenarios"}
    assert quality.count("\n## ") == 3
    wins = [(a, n) for a, b in heldout["agents"].items() for n, s in b["slices"].items()
            if s["n"] and s["learned"]["brier"] < s["frozen"]["brier"]]
    assert wins and notes_about(heldout, "learned does not beat frozen")   # both outcomes are reported, not just the good one
    out = capsys.readouterr().out
    assert "wrote" in out and "heldout.json" in out and "quality.md" in out


def test_demo_is_deterministic(tmp_path):
    from quality.cli import main

    for sub in ("a", "b"):
        main(["--demo", "--out", str(tmp_path / sub)])
    strip = lambda p: [l for l in p.read_text(encoding="utf-8").splitlines() if "generated_at" not in l and "Generated" not in l]  # noqa: E731
    assert strip(tmp_path / "a" / "heldout.json") == strip(tmp_path / "b" / "heldout.json")


def test_without_a_database_the_cli_fails_clearly_not_with_a_traceback(tmp_path, monkeypatch, capsys):
    from quality.cli import main

    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:nope@127.0.0.1:1/none")
    assert main(["--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "could not read scored calls" in err and "--demo" in err and "Traceback" not in err
    assert not (tmp_path / "heldout.json").exists()                # it did not write an empty report as if it were real


def test_attempted_flag_is_validated(tmp_path):
    from quality.cli import main

    with pytest.raises(SystemExit):
        main(["--demo", "--out", str(tmp_path), "--attempted", "fundamentals"])
    assert main(["--demo", "--out", str(tmp_path), "--attempted", "fundamentals=1000"]) == 0
