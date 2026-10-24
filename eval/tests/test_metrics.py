"""accuracy, Brier, calibration, overconfidence, valid-JSON rate, evidence match."""
from __future__ import annotations

import math
from datetime import date

import pytest

from eval import metrics as M
from eval.tests.helpers import make_call, make_scored, six_binary


def test_accuracy_and_brier_on_six_hand_computed_records():
    s = six_binary()
    # correct on rows 1, 3, 5, 6 -> 4 of 6
    assert M.accuracy(s) == pytest.approx(4 / 6, abs=1e-6)
    # 0.04 + 0.36 + 0.09 + 0.81 + 0.25 + 0.09 = 1.64, over 6
    assert M.mean_brier(s) == pytest.approx(1.64 / 6, abs=1e-6)
    assert round(M.accuracy(s), 6) == 0.666667 and round(M.mean_brier(s), 6) == 0.273333


def test_the_real_graders_brier_agrees_with_the_hand_numbers():
    briers = [round(x.grade.brier, 6) for x in six_binary()]
    assert briers == [0.04, 0.36, 0.09, 0.81, 0.25, 0.09]


def test_overconfidence_gap_is_mean_confidence_minus_accuracy():
    s = six_binary()
    assert M.mean_confidence(s) == pytest.approx(0.7, abs=1e-6)             # (0.8+0.6+0.7+0.9+0.5+0.7)/6
    assert M.overconfidence_gap(s) == pytest.approx(0.7 - 4 / 6, abs=1e-6)  # 0.033333
    # an agent that is always 90% sure and half right is overconfident by 0.4
    sure = [make_scored("yes", prob=0.9), make_scored("no", prob=0.9)]
    assert M.overconfidence_gap(sure) == pytest.approx(0.4, abs=1e-6)


def test_calibration_bins_on_the_six_records():
    bins = M.calibration_bins(six_binary(), n_bins=5)
    assert [(b["lo"], b["hi"], b["n"]) for b in bins] == [(0.0, 0.2, 0), (0.2, 0.4, 0), (0.4, 0.6, 1),
                                                          (0.6, 0.8, 3), (0.8, 1.0, 2)]
    assert bins[0]["mean_confidence"] is None and bins[0]["accuracy"] is None   # empty bin: None, not NaN
    assert bins[2]["mean_confidence"] == pytest.approx(0.5) and bins[2]["accuracy"] == pytest.approx(1.0)
    assert bins[3]["mean_confidence"] == pytest.approx(2.0 / 3) and bins[3]["accuracy"] == pytest.approx(2 / 3)
    assert bins[4]["mean_confidence"] == pytest.approx(0.85) and bins[4]["accuracy"] == pytest.approx(0.5)
    assert sum(b["n"] for b in bins) == 6


def test_calibration_top_bin_includes_exactly_one_and_bins_have_the_documented_keys():
    s = [make_scored("yes", prob=1.0), make_scored("yes", prob=0.0)]
    bins = M.calibration_bins(s, n_bins=5)
    assert bins[4]["n"] == 1 and bins[0]["n"] == 1
    assert set(bins[0]) == {"lo", "hi", "n", "mean_confidence", "accuracy"}
    with pytest.raises(ValueError):
        M.calibration_bins(s, n_bins=0)


def test_unresolvable_is_excluded_from_accuracy_and_brier_and_counted():
    s = six_binary() + [make_scored("unresolvable", company="anon_050"), make_scored("unresolvable", company="anon_049")]
    assert M.n_unresolvable(s) == 2
    assert len(M.resolved(s)) == 6
    assert M.accuracy(s) == pytest.approx(4 / 6, abs=1e-6)       # unchanged by the two extra records
    assert M.mean_brier(s) == pytest.approx(1.64 / 6, abs=1e-6)
    assert M.mean_confidence(s) == pytest.approx(0.7, abs=1e-6)
    assert sum(b["n"] for b in M.calibration_bins(s)) == 6


def test_nothing_to_measure_is_none_never_nan():
    for empty in ([], [make_scored("unresolvable")]):
        assert M.accuracy(empty) is None and M.mean_brier(empty) is None
        assert M.overconfidence_gap(empty) is None and M.mean_confidence(empty) is None
        assert all(b["n"] == 0 and b["accuracy"] is None for b in M.calibration_bins(empty))


def test_bucket_calls_are_scored_with_the_multiclass_brier():
    s = [make_scored("base", agent="scenarios", answer="base", prob=0.8),   # right
         make_scored("bull", agent="scenarios", answer="base", prob=0.8)]   # wrong
    assert M.accuracy(s) == 0.5
    # right: (0.8-1)^2 + 0.1^2 + 0.1^2 = 0.06;  wrong: 0.1^2 + 0.8^2 + (0.1-1)^2 = 1.46
    assert M.mean_brier(s) == pytest.approx((0.06 + 1.46) / 2, abs=1e-6)


def test_valid_json_rate_is_calls_over_attempts():
    calls = [make_call(company=f"anon_{i:03d}") for i in range(1, 10)]
    assert M.valid_json_rate(calls, attempted=10) == pytest.approx(0.9)
    assert M.valid_json_rate(calls, attempted=9) == 1.0
    assert M.valid_json_rate([], attempted=5) == 0.0
    assert M.valid_json_rate([], attempted=0) is None            # no attempts: nothing to say
    with pytest.raises(ValueError):                             # more calls than attempts is a bookkeeping error
        M.valid_json_rate(calls, attempted=3)


BUNDLE = {"metrics": [{"name": "fcf_margin_ttm", "value": 0.142}, {"name": "roic", "value": 0.09}]}


def _evidence(metric, value):
    return {"metric": metric, "value": value, "as_of": "2019-06-30"}


def test_evidence_match_rate_counts_calls_whose_values_equal_the_bundle():
    good = make_call(company="anon_001", evidence=[_evidence("fcf_margin_ttm", 0.142)])
    bad_value = make_call(company="anon_002", evidence=[_evidence("fcf_margin_ttm", 0.9)])
    bad_name = make_call(company="anon_003", evidence=[_evidence("not_a_metric", 0.1)])
    none_given = make_call(company="anon_004")
    bundles = {("fundamentals", c.company_id, c.as_of): BUNDLE for c in (good, bad_value, bad_name, none_given)}
    assert M.evidence_match_rate([good, bad_value, bad_name, none_given], bundles) == pytest.approx(2 / 4)


def test_evidence_match_skips_calls_whose_bundle_is_missing_and_accepts_a_function():
    a = make_call(company="anon_001", evidence=[_evidence("roic", 0.09)])
    b = make_call(company="anon_002", evidence=[_evidence("roic", 0.5)])
    only_a = {("fundamentals", "anon_001", a.as_of): BUNDLE}
    assert M.evidence_match_rate([a, b], only_a) == 1.0          # b cannot be checked, so it is not counted
    assert M.evidence_match_rate([b], only_a) is None            # nothing could be checked at all
    fn = lambda agent, company, as_of: BUNDLE if company == "anon_002" else None  # noqa: E731
    assert M.evidence_match_rate([a, b], fn) == 0.0


def test_evidence_match_allows_only_the_runners_tolerance():
    close = make_call(evidence=[_evidence("roic", 0.09 + 1e-12)])
    off = make_call(company="anon_002", evidence=[_evidence("roic", 0.09 + 1e-6)])
    bundles = {("fundamentals", c.company_id, c.as_of): BUNDLE for c in (close, off)}
    assert M.evidence_match_rate([close], bundles) == 1.0
    assert M.evidence_match_rate([off], bundles) == 0.0


def test_no_function_returns_nan():
    for value in (M.accuracy([]), M.mean_brier([]), M.overconfidence_gap([]), M.valid_json_rate([], 0),
                  M.evidence_match_rate([], {})):
        assert value is None or not math.isnan(value)
