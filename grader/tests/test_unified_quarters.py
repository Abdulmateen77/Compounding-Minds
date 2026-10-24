"""The grader and the metrics engine must see the same quarters, or an agent is marked on numbers it was
never shown. Found on real data: the grader knew nothing of derived operating income and 52-week calendars."""
from datetime import date

import pytest

from grader.facts import quarter_table
from grader.rules import rules_outcome
from metrics.context import Context
from metrics.tests import factory as F
from schemas import AgentCall

AS_OF = date(2018, 3, 31)       # after the FY2017 10-K (Feb 2018), before the Q1 2018 10-Q (May 2018)


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


def _call():
    return AgentCall.model_validate(dict(
        call_id="c1", run_id="r1", agent="fundamentals", company_id="anon_001", as_of=AS_OF.isoformat(),
        horizon="next_quarter",
        claim=dict(type="binary", question_id="fcf_margin_improves_next_q", answer="yes", probability=0.6),
        confidence=0.6, reasoning=["x"], evidence=[], principles_used=[], tool_calls=0, model="m"))


def test_the_grader_reads_the_same_quarters_as_the_metrics_engine():
    F.install(F.build_facts())
    ctx = Context("anon_001", AS_OF)
    for concept in ("revenue", "op_cash_flow", "capex", "operating_income"):
        grader_view = {q.period_end: q.value for q in quarter_table("anon_001", [concept], AS_OF)[concept]}
        engine_view = {e: q.value for e, q in ctx.quarters(concept).items()}
        assert grader_view == engine_view, concept


def test_a_company_that_never_tags_operating_income_is_still_gradable():
    F.install(F.build_facts(operating_income=None))        # EBIT is derived from pre-tax + interest
    outcome, info = rules_outcome(_call())
    assert outcome in ("yes", "no"), info


def test_derived_operating_income_gives_the_same_verdict_as_a_tagged_one():
    F.install(F.build_facts())
    tagged = rules_outcome(_call())
    F.install(F.build_facts(operating_income=None))
    derived = rules_outcome(_call())
    assert tagged[0] == derived[0]
    assert tagged[1]["q0"] == pytest.approx(derived[1]["q0"]) and tagged[1]["q1"] == pytest.approx(derived[1]["q1"])
