from datetime import date

import pytest

from eval.baselines import base_rate_prediction, brier_for, score, score_baselines
from eval.split import add_quarters, make_split, pick_held_out, quarter_ends

COMPANIES = [f"anon_{i:03d}" for i in range(1, 51)]


def test_quarter_math():
    qs = quarter_ends(2018, 2024)
    assert len(qs) == 28 and qs[0] == date(2018, 3, 31) and qs[-1] == date(2024, 12, 31)
    assert add_quarters(date(2022, 12, 31), 1) == date(2023, 3, 31)
    assert add_quarters(date(2022, 9, 30), 4) == date(2023, 9, 30)


def test_split_is_deterministic_disjoint_and_sized():
    a, b = make_split(COMPANIES), make_split(list(reversed(COMPANIES)))
    assert a == b
    assert len(a.held_out_companies) == 10 and not set(a.held_out_companies) & set(a.train_companies)
    assert len(a.train_companies) + len(a.held_out_companies) == 50
    assert a.train_end == date(2022, 12, 31) and a.held_out_quarters[0] == date(2023, 3, 31)
    assert pick_held_out(COMPANIES) == list(a.held_out_companies)


def test_split_rejects_bad_input():
    with pytest.raises(ValueError):
        make_split(COMPANIES[:3], 3)
    with pytest.raises(ValueError):
        make_split(COMPANIES, held_out_years=(2022, 2024))


def test_scoring_and_baselines():
    assert brier_for("binary", "yes", 1.0, "yes") == 0 and brier_for("binary", "no", 1.0, "yes") == 1
    s = score("binary", [("yes", 0.8, "yes"), ("no", 0.7, "yes")])
    assert s["n"] == 2 and s["accuracy"] == 0.5
    assert score("binary", [])["accuracy"] is None
    assert base_rate_prediction(["no", "no", "yes"]) == ("no", 2 / 3)
    assert base_rate_prediction([]) is None
    b = score_baselines("binary", ["yes", "no"], ["no", "no", "yes"])
    assert b["always_yes"]["accuracy"] == 0.5 and b["base_rate"]["answer"] == "no"
    bb = score_baselines("bucket", ["base", "bull"], ["bull", "bull", "bear"])
    assert "always_base" in bb and bb["base_rate"]["answer"] == "bull"
    assert score_baselines("binary", ["yes"], [])["base_rate"]["accuracy"] is None
