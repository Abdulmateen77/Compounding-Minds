"""The leak guard, and a sweep proving the real prompts are clean."""
from datetime import date

import pytest

from agents.entry import Entry
from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.leakcheck import find_leaks
from agents.runner import build_messages
from ingest.universe import load_universe
from metrics import get_metrics
from metrics.tests import factory as F
from store.stubs import get_metrics_stub, list_stub_cases

AFTER = date(2019, 3, 1)


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


# ---------------------------------------------------------------- the detector
@pytest.mark.parametrize("text,expect", [
    ("revenue_growth_yoy = 0.0831 ratio", []),
    ("Q-3 FCF margin rose, Q0 fell", []),
    ("In 2019 revenue grew", ["year 2019"]),
    ("filed 0000320193-18-000070", ["accession number 0000320193-18-000070"]),
    ("this is AAPL again", ["ticker AAPL"]),
    ("This is Home Depot again", ["company name Home Depot"]),
    ("FY2019 was strong", ["year 2019"]),
    ("(2019) and in 2019.", ["year 2019", "year 2019"]),
    ("Nvidia and NVIDIA", ["company name NVIDIA"]),
])
def test_find_leaks(text, expect):
    assert find_leaks(text) == expect


def test_single_letter_tickers_and_ordinary_words_are_not_false_alarms():
    # F (Ford), M (Macy's), and capitalised ordinary words must not trigger
    assert find_leaks("F and M are ordinary letters. Hit the margin target. GENERAL ratio of x to y.") == []


@pytest.mark.parametrize("value", ["0.2018", "0.1999", "12.2019", "1.9500", "-0.2005", "0.19", "x = 0.2018 ratio"])
def test_decimal_metric_values_that_look_like_years_do_not_trip_it(value):
    # metric values are rounded to 4 decimals, so 0.19xx and 0.20xx are common: they are not years
    assert find_leaks(f"fcf_margin_ttm = {value} ratio") == []


def test_no_universe_ticker_or_name_appears_in_any_principles_file():
    from pathlib import Path
    for f in (Path(__file__).resolve().parents[2] / "principles").glob("*.md"):
        text = f.read_text()
        bad = [p for p in find_leaks(text) if not p.startswith("year")]   # citations name years, e.g. a 1986 letter
        assert bad == [], f"{f.name}: {bad}"


# ---------------------------------------------------------------- the real prompts are clean
@pytest.mark.parametrize("agent", ["fundamentals", "risk", "scenarios"])
def test_every_stub_prompt_is_clean(agent):
    for company, as_of in list_stub_cases(agent):
        msgs = build_messages(agent, company, as_of, get_metrics_stub(company, agent, as_of), [])
        assert find_leaks(msgs[1]["content"]) == [], (agent, company, as_of)


@pytest.mark.parametrize("agent", ["fundamentals", "risk", "scenarios"])
def test_a_prompt_built_from_real_metrics_is_clean_even_though_inputs_hold_accessions(agent):
    F.install(F.build_facts(), macro=F.build_macro())
    bundle = get_metrics("anon_001", agent, AFTER)
    assert any(m["inputs"] for m in bundle["metrics"])        # accessions exist in the bundle...
    msgs = build_messages(agent, "anon_001", AFTER, bundle, [])
    assert find_leaks(msgs[1]["content"]) == []                # ...but never reach the prompt


def test_the_universe_contains_the_names_the_guard_looks_for():
    assert len(load_universe()) == 50


# ---------------------------------------------------------------- the guard in the entry point
def test_a_lesson_that_names_a_company_blocks_the_call_and_the_model_is_never_asked(tmp_path):
    asked = []
    entry = Entry(ScriptedGateway(lambda a, m: asked.append(1) or "{}"), FakeModelUpdater(tmp_path),
                  metrics_fn=get_metrics_stub)
    a = entry.attempt("fundamentals", "anon_001", date(2019, 6, 30),
                      lessons=["Tesla ignored rising capex, so discount its FCF"])
    assert a.status == "blocked" and a.call is None and a.leaks == ["company name Tesla"]
    assert asked == []


def test_a_lesson_that_carries_a_year_is_blocked_or_masked_never_sent_raw(tmp_path):
    asked = []
    entry = Entry(ScriptedGateway(lambda a, m: asked.append(m) or "{}"), FakeModelUpdater(tmp_path),
                  metrics_fn=get_metrics_stub)
    entry.attempt("fundamentals", "anon_001", date(2019, 6, 30), lessons=["Capex jumped in 2019, discount FCF"])
    for messages in asked:                                    # whatever was sent must be clean
        assert find_leaks(messages[-1]["content"]) == []


def test_a_clean_prompt_goes_through(tmp_path):
    asked = []
    entry = Entry(ScriptedGateway(lambda a, m: asked.append(1) or "not json"), FakeModelUpdater(tmp_path),
                  metrics_fn=get_metrics_stub)
    a = entry.attempt("fundamentals", "anon_001", date(2019, 6, 30), lessons=["Discount FCF when capex rises"])
    assert a.status == "dropped" and len(asked) == 2          # reached the model (twice: one repair retry)
