"""The two baselines, and the rule that base_rate never sees held-out data."""
from __future__ import annotations

from datetime import date

import pytest

from eval.baselines import (BASE_RATE, Pick, always_yes_pick, fit_base_rate, score_outcomes, score_pick)
from eval.tests.helpers import make_scored

HELD = {"anon_090"}


def train_case(outcome, i, agent="fundamentals", as_of=date(2019, 6, 30), **kw):
    return make_scored(outcome, agent=agent, company=f"anon_{i:03d}", as_of=as_of, **kw)


def test_always_yes_is_yes_for_binary_and_base_for_buckets_with_probability_one():
    assert always_yes_pick("binary") == Pick("yes", 1.0)
    assert always_yes_pick("bucket") == Pick("base", 1.0)


def test_always_yes_scores_by_hand():
    # outcomes yes, no, yes, yes -> right 3 of 4. p(yes)=1 so brier is 0 on a yes and 1 on a no: mean 0.25
    acc, brier = score_outcomes(always_yes_pick("binary"), "binary", ["yes", "no", "yes", "yes"])
    assert acc == pytest.approx(0.75) and brier == pytest.approx(0.25)


def test_always_base_on_buckets_scores_by_hand():
    # base: perfect.  bull: 1 (the base bucket) + 1 (the bull bucket) = 2.  So outcomes [base, bull] -> 1.0
    acc, brier = score_outcomes(always_yes_pick("bucket"), "bucket", ["base", "bull"])
    assert acc == 0.5 and brier == pytest.approx(1.0)


def test_base_rate_picks_the_most_common_training_outcome_with_its_frequency():
    scored = [train_case(o, i) for i, o in enumerate(["yes", "yes", "yes", "no"], 1)]
    fit = fit_base_rate(scored, HELD)
    assert fit.picks["fundamentals"] == Pick("yes", 0.75) and fit.n_train["fundamentals"] == 4
    # scored on [yes, no]: (0.75-1)^2 = 0.0625 and (0.75-0)^2 = 0.5625 -> mean 0.3125, accuracy 0.5
    acc, brier = score_outcomes(fit.picks["fundamentals"], "binary", ["yes", "no"])
    assert acc == pytest.approx(0.5) and brier == pytest.approx(0.3125)


def test_base_rate_for_a_minority_answer_scores_the_probability_of_that_answer():
    fit = fit_base_rate([train_case(o, i) for i, o in enumerate(["no", "no", "no", "yes"], 1)], HELD)
    assert fit.picks["fundamentals"] == Pick("no", 0.75)
    # p(yes) is 0.25. On an outcome of yes: (0.25-1)^2 = 0.5625
    assert score_outcomes(fit.picks["fundamentals"], "binary", ["yes"])[1] == pytest.approx(0.5625)


def test_base_rate_on_buckets_spreads_the_remaining_probability_evenly():
    fit = fit_base_rate([train_case(o, i, agent="scenarios") for i, o in enumerate(["base", "base", "bull", "bear"], 1)], HELD)
    assert fit.picks["scenarios"] == Pick("base", 0.5)
    # outcome bear: bear (0.25-1)^2 + base (0.5-0)^2 + bull (0.25-0)^2 = 0.5625 + 0.25 + 0.0625 = 0.875
    assert score_pick(fit.picks["scenarios"], "bucket", "bear") == (False, pytest.approx(0.875))


def test_base_rate_ties_go_to_the_alphabetically_first_outcome_so_it_is_deterministic():
    fit = fit_base_rate([train_case("yes", 1), train_case("no", 2)], HELD)
    assert fit.picks["fundamentals"] == Pick("no", 0.5)


def test_changing_a_heldout_company_outcome_does_not_change_the_baseline():
    base = [train_case(o, i) for i, o in enumerate(["yes", "yes", "no"], 1)]
    held_company = lambda o: make_scored(o, company="anon_090", as_of=date(2019, 6, 30))  # noqa: E731
    a = fit_base_rate(base + [held_company("yes")] * 5, HELD)
    b = fit_base_rate(base + [held_company("no")] * 5, HELD)
    assert a.picks == b.picks == fit_base_rate(base, HELD).picks
    assert a.n_train == b.n_train == {"fundamentals": 3}


def test_changing_a_heldout_year_outcome_does_not_change_the_baseline():
    base = [train_case(o, i) for i, o in enumerate(["yes", "yes", "no"], 1)]
    later = lambda o, i: make_scored(o, company=f"anon_{i:03d}", as_of=date(2023, 3, 31))  # noqa: E731
    a = fit_base_rate(base + [later("no", i) for i in range(10, 20)], HELD)
    b = fit_base_rate(base + [later("yes", i) for i in range(10, 20)], HELD)
    assert a.picks == b.picks == fit_base_rate(base, HELD).picks


def test_a_training_call_settled_by_a_filing_after_the_training_window_is_not_used():
    """A Q4 2022 call about the next four quarters resolves in 2023-24: that outcome is held-out-window
    information, so the baseline must not fit on it."""
    base = [train_case(o, i) for i, o in enumerate(["yes", "yes", "no"], 1)]
    late = lambda o, i: train_case(o, i, as_of=date(2022, 12, 31), resolution=date(2023, 12, 31))  # noqa: E731
    a = fit_base_rate(base + [late("no", i) for i in range(10, 20)], HELD)
    b = fit_base_rate(base + [late("yes", i) for i in range(10, 20)], HELD)
    assert a.picks == b.picks == fit_base_rate(base, HELD).picks
    assert a.excluded_late == {"fundamentals": 10}
    assert any("left out 10" in n for n in a.notes)


def test_a_missing_resolution_date_is_used_but_reported():
    fit = fit_base_rate([train_case("yes", 1, resolution=None), train_case("no", 2)], HELD)
    assert fit.n_train["fundamentals"] == 2
    assert fit.unknown_resolution == {"fundamentals": 1}
    assert any("no resolution date" in n for n in fit.notes)


def test_unresolvable_cases_do_not_enter_the_fit():
    scored = [train_case("yes", 1), train_case("unresolvable", 2), train_case("unresolvable", 3)]
    fit = fit_base_rate(scored, HELD)
    assert fit.picks["fundamentals"] == Pick("yes", 1.0) and fit.n_train["fundamentals"] == 1


def test_the_same_case_seen_by_learned_and_frozen_counts_once():
    both = [train_case("no", 1, variant="learned"), train_case("no", 1, variant="frozen"),
            train_case("yes", 2, variant="learned"), train_case("yes", 2, variant="frozen")]
    fit = fit_base_rate(both, HELD)
    assert fit.n_train["fundamentals"] == 2 and fit.picks["fundamentals"] == Pick("no", 0.5)


def test_the_fit_is_per_agent():
    scored = [train_case("yes", 1), train_case("bull", 2, agent="scenarios"), train_case("bull", 3, agent="scenarios")]
    fit = fit_base_rate(scored, HELD)
    assert fit.picks == {"fundamentals": Pick("yes", 1.0), "scenarios": Pick("bull", 1.0)}


def test_no_training_cases_means_no_pick_and_a_null_score():
    fit = fit_base_rate([make_scored("yes", company="anon_090")], HELD)   # only a held-out company
    assert fit.picks == {}
    assert score_outcomes(None, "binary", ["yes"]) == (None, None)
    assert score_outcomes(Pick("yes", 1.0), "binary", []) == (None, None)


def test_the_baseline_name_is_the_json_key():
    assert BASE_RATE == "base_rate"
