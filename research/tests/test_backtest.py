"""The back-test's arithmetic: quarter list, rank correlation, buckets."""
import json
from datetime import date

import pytest

from research import backtest as B


def test_quarter_ends_cover_the_window_inclusively():
    qs = B.quarter_ends(date(2018, 3, 31), date(2019, 6, 30))
    assert qs == [date(2018, 3, 31), date(2018, 6, 30), date(2018, 9, 30), date(2018, 12, 31), date(2019, 3, 31), date(2019, 6, 30)]
    assert len(B.quarter_ends()) == 24


def test_spearman_is_one_for_a_monotone_relation_and_handles_ties_and_small_samples():
    xs = list(range(20))
    assert B.spearman(xs, [x * x for x in xs]) == pytest.approx(1.0)
    assert B.spearman(xs, [-x for x in xs]) == pytest.approx(-1.0)
    assert B.spearman([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], list(range(10))) is None      # no variation in x
    assert B.spearman([1, 2, 3], [1, 2, 3]) is None                                  # too few points


def test_the_shuffle_test_calls_a_strong_relation_rare_and_noise_ordinary():
    xs = list(range(40))
    strong = B.permutation_p(xs, xs, 1.0, n=300)
    assert strong < 0.02
    import random
    rng = random.Random(1)
    noise = [rng.random() for _ in xs]
    rho = B.spearman(xs, noise)
    assert B.permutation_p(xs, noise, rho, n=300) > 0.05


def test_summary_buckets_the_fits_and_averages_each_outcome(tmp_path):
    rows = []
    for i in range(30):
        fit = i / 29
        rows.append({"company_id": "a", "as_of": "2019-03-31", "held_out": i % 5 == 0, "fit": {"buffett": fit, "munger": fit},
                     "growth_next": fit * 0.2, "fcf_margin_next": None, "distress": 1 if fit < 0.3 else 0})
    p = tmp_path / "b.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    s = B.summarise(p)
    growth = next(t for t in s["tests"] if t["outcome"].startswith("Revenue growth"))
    high, mid, low = growth["buckets"]
    assert high["mean"] > mid["mean"] > low["mean"] and growth["spearman"] == pytest.approx(1.0)
    distress = next(t for t in s["tests"] if t["lens"] == "munger")
    assert distress["buckets"][2]["mean"] > distress["buckets"][0]["mean"] and distress["spearman"] < 0
    assert next(t for t in s["tests"] if t["outcome"].startswith("Free-cash"))["n"] == 0          # all None: skipped, not zero
    assert B.summarise(p, held_out=True)["rows"] == 6
    assert "company-quarters" in B.format_summary(s)
