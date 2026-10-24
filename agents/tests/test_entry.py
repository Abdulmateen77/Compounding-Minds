"""Entry: real metrics reach the agent, bad bundles are skipped, and the evidence check works on them."""
import json
from datetime import date

import pytest

from agents.entry import Entry, default_metrics_fn
from agents.gateway import FakeModelUpdater, ScriptedGateway
from metrics import get_metrics
from metrics.tests import factory as F
from store.stubs import get_metrics_stub

AFTER = date(2019, 3, 1)


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


def echo_reply(agent, messages):
    """A model that answers yes and cites the first metric it was shown, with the exact value."""
    user = messages[-1]["content"]
    line = next(l for l in user.splitlines() if l.startswith("- ") and " = " in l and "LESSONS" not in l
                and l[2:].split(" = ")[0].replace("_", "").isalnum())
    name, rest = line[2:].split(" = ")
    value = float(rest.split()[0])
    return json.dumps({"claim": {"type": "binary", "question_id": "x", "answer": "yes", "probability": 0.6},
                       "confidence": 0.6, "reasoning": [f"{name} is as shown"],
                       "evidence": [{"metric": name, "value": value}], "principles_used": ["buffett.01"]})


def test_a_real_bundle_goes_to_the_agent_and_its_evidence_passes_the_check(tmp_path):
    F.install(F.build_facts(), macro=F.build_macro())
    entry = Entry(ScriptedGateway(echo_reply), FakeModelUpdater(tmp_path), metrics_fn=get_metrics)
    a = entry.attempt("fundamentals", "anon_001", AFTER)
    assert a.status == "ok" and a.call.agent == "fundamentals" and a.call.company_id == "anon_001"
    assert a.call.evidence[0].metric == "fcf_margin_ttm"      # a real metric, value copied exactly


def test_an_unusable_bundle_is_skipped_and_the_model_is_never_called(tmp_path):
    F.install(F.build_facts(cash=None))                        # risk: cash, auditor, going-concern all missing
    asked = []
    entry = Entry(ScriptedGateway(lambda a, m: asked.append(1) or "{}"), FakeModelUpdater(tmp_path), metrics_fn=get_metrics)
    a = entry.attempt("risk", "anon_001", AFTER)
    assert a.status == "skipped" and a.call is None and len(a.missing) >= 3
    assert asked == []


def test_an_invalid_reply_is_reported_as_dropped_not_skipped(tmp_path):
    F.install(F.build_facts())
    entry = Entry(ScriptedGateway(lambda a, m: "not json"), FakeModelUpdater(tmp_path), metrics_fn=get_metrics)
    assert entry.attempt("fundamentals", "anon_001", AFTER).status == "dropped"


def test_a_company_with_no_data_is_skipped(tmp_path):
    F.install(F.build_facts())
    entry = Entry(ScriptedGateway(echo_reply), FakeModelUpdater(tmp_path), metrics_fn=get_metrics)
    assert entry.attempt("fundamentals", "anon_042", AFTER).status == "skipped"


def test_stub_bundles_still_work_for_development(tmp_path):
    entry = Entry(ScriptedGateway(echo_reply), FakeModelUpdater(tmp_path), metrics_fn=get_metrics_stub)
    assert entry.attempt("fundamentals", "anon_001", date(2019, 6, 30)).status == "ok"


def test_use_stubs_switch(monkeypatch):
    monkeypatch.setenv("USE_STUBS", "1")
    assert default_metrics_fn() is get_metrics_stub
    monkeypatch.setenv("USE_STUBS", "0")
    assert default_metrics_fn() is get_metrics


def test_run_returns_just_the_call(tmp_path):
    F.install(F.build_facts())
    entry = Entry(ScriptedGateway(echo_reply), FakeModelUpdater(tmp_path), metrics_fn=get_metrics)
    assert entry.run("fundamentals", "anon_001", AFTER).agent == "fundamentals"
    assert entry.run("fundamentals", "anon_042", AFTER) is None
