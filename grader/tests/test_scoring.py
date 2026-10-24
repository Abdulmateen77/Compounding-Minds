import pytest
from grader.scoring import brier_binary, brier_multiclass, bucket_for_growth, p_yes


def test_buckets_fixed_boundaries():
    assert bucket_for_growth(-0.01) == "bear"
    assert bucket_for_growth(0.0) == "base"
    assert bucket_for_growth(0.099) == "base"
    assert bucket_for_growth(0.10) == "bull"


def test_p_yes_flips_for_no_answers():
    assert p_yes("yes", 0.7) == 0.7
    assert p_yes("no", 0.7) == pytest.approx(0.3)


def test_binary_brier():
    assert brier_binary(0.68, True) == pytest.approx(0.1024)
    assert brier_binary(0.68, False) == pytest.approx(0.4624)


def test_multiclass_brier_perfect_and_worst():
    assert brier_multiclass("bull", 1.0, "bull") == 0.0
    assert brier_multiclass("bull", 1.0, "bear") == pytest.approx(2.0)
