"""One fixture + test per question_id (README 7.1), offline. Fundamentals, Scenarios and Risk are
real rules; the other three are stubs and the tests say so."""
import logging
from datetime import date

import pytest

from grader import rules
from grader.grade import grade, grade_many
from grader.risk import resolve_distress
from grader.sapling import SaplingClient
from grader.scoring import accuracy
from grader.tests import fixtures as fx
from store import queries
from store.queries import InMemoryBackend

FQ, SQ, RQ = "fcf_margin_improves_next_q", "revenue_bucket_next_4q", "distress_event_12m"


@pytest.fixture(autouse=True)
def _reset_store():
    yield
    queries.set_backend(InMemoryBackend())


def use(rows=(), events=()):
    queries.set_backend(InMemoryBackend(facts=rows, events=events))


def fund_rows(oi_last=20, ocf_last=25, n=10):
    return fx.company([100] * n, [10] * (n - 1) + [oi_last], [15] * (n - 1) + [ocf_last], [5] * n)


# ---- Fundamentals ----------------------------------------------------------------------------
def test_fundamentals_yes_when_both_margins_rise():
    use(fund_rows())
    out, info = rules.rules_outcome(fx.call(FQ, "yes"))
    assert out == "yes"
    assert info["latest_quarter"] == "2019-03-31" and info["next_quarter"] == "2019-06-30"
    assert info["q0"]["operating_margin"] == pytest.approx(0.10) and info["q1"]["operating_margin"] == pytest.approx(0.125)
    assert info["resolution_date"] == "2019-08-09"  # the 10-Q filing date, not the quarter end


def test_fundamentals_no_when_only_one_margin_rises():
    use(fund_rows(oi_last=5))  # fcf margin up, operating margin down
    out, info = rules.rules_outcome(fx.call(FQ, "yes"))
    assert out == "no" and info["decisive_metrics"] == ["operating_margin"]


def test_fundamentals_uses_the_q4_derived_from_the_10k():
    # as_of 2019-09-30: Q0 = Jun 2019, next = Q4 (FY - 9M) visible only at the 10-K date.
    use(fund_rows(n=12))
    out, info = rules.rules_outcome(fx.call(FQ, "no", as_of=date(2019, 9, 30)))
    assert info["next_quarter"] == "2019-09-30" or info["next_quarter"] == "2019-12-31"
    assert out in ("yes", "no") and info["resolution_date"] in ("2019-11-09", "2020-02-29")


def test_fundamentals_next_filing_not_visible_is_unresolvable():
    use(fund_rows(n=9))  # nothing after Mar 2019
    out, info = rules.rules_outcome(fx.call(FQ, "yes"))
    assert out == "unresolvable" and "not filed" in info["reason"]
    assert info["resolution_date"] == "2020-02-25"  # as_of + 240d: where we stopped looking


def test_fundamentals_missing_concept_is_unresolvable():
    rows = [r for r in fund_rows() if r["concept"] != "capex"]
    use(rows)
    out, info = rules.rules_outcome(fx.call(FQ, "yes"))
    assert out == "unresolvable" and "capex" in info["reason"]


# ---- Restatement: grade on the value known at resolution -------------------------------------
def test_restatement_after_resolution_is_ignored():
    rows = fund_rows()  # Q1 improves: yes
    rows = fx.restate(rows, "operating_income", date(2019, 6, 30), -50, date(2019, 12, 1), "acc-restated-late")
    use(rows)
    out, info = rules.rules_outcome(fx.call(FQ, "yes"))
    assert out == "yes" and info["resolution_date"] == "2019-08-09"
    assert "acc-restated-late" not in info["accessions"]


def test_restatement_filed_by_resolution_date_is_used():
    base = fund_rows()
    use(base)
    assert rules.rules_outcome(fx.call(FQ, "yes"))[0] == "yes"
    # The oldest quarter in Q0's TTM window is restated up (filed before Q1's 10-Q): Q1's TTM now
    # drops a bigger quarter, so the operating margin falls and the grade follows the restated value.
    restated = fx.restate(base, "operating_income", date(2018, 6, 30), 30, date(2019, 8, 1), "acc-restated-q0")
    use(restated)
    out, info = rules.rules_outcome(fx.call(FQ, "yes"))
    assert out == "no" and "operating_margin" in info["decisive_metrics"]


# ---- Scenarios -------------------------------------------------------------------------------
@pytest.mark.parametrize("fwd,bucket", [(120, "bull"), (105, "base"), (90, "bear")])
def test_scenarios_bucket_from_actual_growth(fwd, bucket):
    n = 13
    use(fx.company([100] * 9 + [fwd] * 4, [10] * n, [15] * n, [5] * n))
    out, info = rules.rules_outcome(fx.call(SQ, "base", agent="scenarios", claim_type="bucket"))
    assert out == bucket
    assert info["revenue_growth"] == pytest.approx(fwd / 100 - 1)
    assert info["resolution_date"] == "2020-05-10"  # 10-Q for the 4th next quarter (Mar 2020)


def test_scenarios_incomplete_next_four_quarters_unresolvable():
    use(fx.company([100] * 12, [10] * 12, [15] * 12, [5] * 12))
    out, info = rules.rules_outcome(fx.call(SQ, "base", agent="scenarios", claim_type="bucket"))
    assert out == "unresolvable" and info["quarters_found"] == 3


def test_scenarios_thresholds_live_in_config():
    from grader import config
    assert config.BUCKETS["base"] == (0.0, 0.10)


# ---- Risk (distress_event_12m) ---------------------------------------------------------------
def dividends(per_q):
    return fx.cashflow_rows("dividends_paid", dict(zip(fx.Q_ENDS, per_q)))


def clean_10q():
    return [dict(company_id=fx.CID, form="10-Q", items=[], filed_date=date(2019, 8, 9), accession="q",
                 text_ref="clean")]


def distress(rows=(), events=None):
    use(rows, clean_10q() if events is None else events)
    return resolve_distress(fx.call(RQ, "yes", agent="risk"), sapling=SaplingClient(replay_only=True),
                            load_text=lambda e: "Nothing unusual.")


def test_dividend_cut_of_half_is_yes():
    out, info = distress(dividends([10] * 9 + [5] * 4))
    assert out == "yes"
    c = info["components"]["dividend_cut"]
    assert c["result"] == "yes" and c["change"] <= -0.25  # flagged as soon as the TTM falls 25%


def test_dividend_cut_exactly_25_percent_counts_and_20_does_not():
    assert distress(dividends([10] * 9 + [7.5] * 4))[0] == "yes"
    out, info = distress(dividends([10] * 9 + [8] * 4))
    assert out == "no" and info["components"]["dividend_cut"]["result"] == "no"


def test_dividend_cut_filed_after_window_end_is_invisible():
    # the cut shows up in the Jun 2020 TTM, filed Aug 2020, after the 2020-06-30 window end
    assert distress(dividends([10] * 13 + [1] * 2))[0] == "no"


def test_dividend_cut_before_the_call_is_not_counted():
    assert distress(dividends([10] + [4] * 12))[0] == "no"


def test_non_payer_has_no_cut_and_payer_without_new_data_is_unresolvable():
    assert distress([])[0] == "no"
    out, info = distress(dividends([10] * 9))
    assert out == "unresolvable" and info["components"]["dividend_cut"]["result"] == "unresolvable"


def test_auditor_change_item_401_is_yes():
    ev = [dict(company_id=fx.CID, form="8-K", items=["4.01"], filed_date=date(2019, 9, 10), accession="e1", text_ref=None)]
    out, info = distress(events=ev)
    assert out == "yes" and info["components"]["auditor_change"]["accessions"] == ["e1"]
    # an auditor change filed BEFORE the call is not a future event
    ev[0]["filed_date"] = date(2019, 5, 1)
    assert distress(events=ev + clean_10q())[0] == "no"


# ---- stubs (valuation, moat, synthesizer) ----------------------------------------------------
@pytest.mark.parametrize("qid,agent,ctype,answer", [
    ("implied_growth_above_delivered", "valuation", "binary", "yes"),
    ("gross_margin_holds_2pts", "moat", "binary", "yes"),
    ("committee_verdict", "synthesizer", "bucket", "neutral")])
def test_stub_questions_are_marked_stubs(qid, agent, ctype, answer):
    out, info = rules.rules_outcome(fx.call(qid, answer, agent=agent, claim_type=ctype))
    assert info == {"stub": True} and out


def test_unknown_question_raises():
    with pytest.raises(ValueError):
        rules.rules_outcome(fx.call("nope", "yes"))


# ---- unresolvable handling, resolution_date --------------------------------------------------
def test_unresolvable_is_logged_excluded_and_dated(caplog):
    use(fund_rows(n=9))
    ok_rows = fund_rows()
    calls = [fx.call(FQ, "yes", call_id="a")]
    with caplog.at_level(logging.WARNING, logger="grader.unresolvable"):
        grades, n = grade_many(calls, rules.rules_outcome)
    g = grades[0]
    assert n == 1 and g.outcome == "unresolvable" and g.correct is None and g.brier is None
    assert g.resolution_date == date(2020, 2, 25)
    assert "call_id=a" in caplog.text and "not filed" in caplog.text
    use(ok_rows)
    wrong = grade(fx.call(FQ, "no", call_id="b"), rules.rules_outcome)
    assert accuracy(grades + [wrong]) == 0.0  # the unresolvable one does not count as wrong
    assert accuracy(grades) is None


def test_every_grade_has_a_resolution_date():
    for qid, agent, ct, ans in [("committee_verdict", "synthesizer", "bucket", "neutral"),
                                ("gross_margin_holds_2pts", "moat", "binary", "no")]:
        g = grade(fx.call(qid, ans, agent=agent, claim_type=ct), rules.rules_outcome)
        assert g.resolution_date is not None
    use(fund_rows())
    assert grade(fx.call(FQ, "yes"), rules.rules_outcome).resolution_date == date(2019, 8, 9)
