import json
from datetime import date

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.masking import has_calendar_year, mask_dates, relative_quarter
from agents.runner import build_messages, run_agent
from store.stubs import get_metrics_stub

AS_OF = date(2019, 6, 30)


def test_relative_quarters():
    assert relative_quarter(date(2019, 6, 30), AS_OF) == "Q0"
    assert relative_quarter(date(2019, 3, 31), AS_OF) == "Q-1"
    assert relative_quarter(date(2017, 6, 30), AS_OF) == "Q-8"
    assert relative_quarter(date(2019, 12, 31), AS_OF) == "Q+2"


def test_mask_dates_all_forms():
    text = "filed 2019-03-31, peak in 2018Q4, trough Q1 2019, 2019-Q3 guide, since 2017"
    out = mask_dates(text, AS_OF)
    assert out == "filed Q-1, peak in Q-2, trough Q-1, Q+1 guide, since Y-2"
    assert not has_calendar_year(out)


def test_mask_leaves_numbers_alone():
    assert mask_dates("revenue 2019.5 and 20190 units, margin 0.2019", AS_OF) == "revenue 2019.5 and 20190 units, margin 0.2019"


def _with_dated_names(m):
    m = json.loads(json.dumps(m))
    m["metrics"].append({"name": "revenue_2018Q4", "value": 2019.0, "unit": "usd_m since 2017",
                         "as_of": "2019-06-30", "inputs": []})
    return m


def test_prompt_never_shows_as_of_date_or_year():
    m = _with_dated_names(get_metrics_stub("anon_001", "fundamentals", AS_OF))
    lessons = ["In 2019 capex_to_revenue rose after 2019-03-31."]
    msgs = build_messages("fundamentals", "anon_001", AS_OF, m, lessons)
    user, system = msgs[1]["content"], msgs[0]["content"]
    assert "anon_001" in user and "as_of: Q0" in user
    assert not has_calendar_year(user)
    assert "2019-06-30" not in system + user
    assert "revenue_Q-2 = 2019.0 usd_m since Y-2" in user  # value kept, name/unit masked
    assert "In Y0 capex_to_revenue rose after Q-1." in system


def test_evidence_as_of_is_stamped_by_runner(tmp_path):
    def reply(agent, msgs):
        return json.dumps({"claim": {"type": "binary", "question_id": "x", "answer": "no", "probability": 0.6},
                           "confidence": 0.6, "reasoning": ["capex_to_revenue high"],
                           "evidence": [{"metric": "capex_to_revenue", "value": 0.052, "as_of": "Q0"}],
                           "principles_used": []})
    m = get_metrics_stub("anon_001", "fundamentals", AS_OF)
    call = run_agent("fundamentals", "anon_001", AS_OF, m, ScriptedGateway(reply), FakeModelUpdater(tmp_path))
    assert call is not None and call.evidence[0].as_of == AS_OF
