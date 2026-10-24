from datetime import date, datetime, timezone

import pytest

from grader.calibration import track_record
from grader.tests.fixtures import call
from schemas import Grade

FQ = "fcf_margin_improves_next_q"


def pair(cid, conf, correct, res=date(2019, 8, 9), agent="fundamentals", brier=0.1):
    c = call(FQ, "yes", prob=conf, agent=agent, call_id=cid)
    g = Grade(call_id=cid, graded_at=datetime.now(timezone.utc), resolution_date=res,
              outcome="unresolvable" if correct is None else ("yes" if correct else "no"),
              correct=correct, brier=None if correct is None else brier)
    return c, g


def test_record_excludes_unresolvable_and_measures_overconfidence():
    pairs = [pair("a", 0.9, True), pair("b", 0.9, False), pair("c", 0.7, None),
             pair("r", 0.6, True, agent="risk")]
    tr = track_record(pairs)
    f = tr["fundamentals"]
    assert set(tr) == {"fundamentals", "risk"}
    assert f["calls_graded"] == 2 and f["unresolvable"] == 1
    assert f["accuracy"] == 0.5 and f["brier"] == pytest.approx(0.1)
    assert f["overconfidence_gap"] == pytest.approx(0.4)  # says 0.9, right half the time
    top = f["bins"][-1]
    assert top["n"] == 2 and top["accuracy"] == 0.5 and sum(b["n"] for b in f["bins"]) == 2


def test_point_in_time_only_counts_grades_resolved_by_as_of():
    pairs = [pair("early", 0.8, True, res=date(2019, 8, 9)),
             pair("late", 0.8, False, res=date(2020, 2, 1))]
    assert track_record(pairs, as_of=date(2019, 9, 30))["fundamentals"]["accuracy"] == 1.0
    assert track_record(pairs, as_of=date(2020, 3, 31))["fundamentals"]["accuracy"] == 0.5
    assert track_record(pairs, as_of=date(2019, 1, 1)) == {}


def test_confidence_one_lands_in_top_bin_and_empty_bins_are_none():
    b = track_record([pair("x", 1.0, True)])["fundamentals"]["bins"]
    assert b[-1]["n"] == 1 and b[0]["n"] == 0 and b[0]["accuracy"] is None
