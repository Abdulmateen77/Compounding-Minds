import json
from datetime import date
from pathlib import Path

from store.concepts import ALL_TAGS, CONCEPTS, METRIC_INPUTS, TAG_TO_CONCEPT, resolve_concept

STUBS = Path(__file__).resolve().parent.parent / "stubs"


def _stub_metric_names() -> set[str]:
    names: set[str] = set()
    for agent in ("fundamentals", "risk", "scenarios"):
        data = json.loads((STUBS / f"metrics_{agent}.json").read_text())
        for bundle in data["bundles"]:
            names |= {m["name"] for m in bundle["metrics"]}
    return names


def test_every_tag_belongs_to_exactly_one_concept():
    seen: dict[str, str] = {}
    for c in CONCEPTS.values():
        for tag in c.tags:
            assert tag not in seen, f"{tag} is in both {seen[tag]} and {c.key}"
            seen[tag] = c.key
    assert ALL_TAGS == set(TAG_TO_CONCEPT)


def test_metric_inputs_cover_exactly_the_metrics_agents_are_shown():
    # The stubs are the contract with agents and principles/: same names, no more, no less.
    assert set(METRIC_INPUTS) == _stub_metric_names()


def test_every_metric_input_is_a_known_concept_event_or_macro():
    for metric, inputs in METRIC_INPUTS.items():
        for name in inputs:
            assert name in CONCEPTS or name.startswith(("event:", "macro:")), f"{metric}: unknown input {name}"


def test_cash_flow_items_are_flagged_cumulative():
    cum = {k for k, c in CONCEPTS.items() if c.cumulative_in_10q}
    assert {"op_cash_flow", "capex", "depreciation_amortization", "dividends_paid"} <= cum
    assert "revenue" not in cum and "operating_income" not in cum


def _row(tag_period, value, filed, accession="a"):
    start, end = tag_period
    return {"period_start": start, "period_end": end, "value": value, "filed_date": filed,
            "accession": accession, "form": "10-K", "unit": "USD"}


def test_resolve_prefers_best_tag_per_period_and_survives_a_tag_switch():
    y17 = (date(2017, 1, 1), date(2017, 12, 31))
    y18 = (date(2018, 1, 1), date(2018, 12, 31))
    rows = {
        # old tag only reports 2017; new tag reports 2017 and 2018
        "SalesRevenueNet": [_row(y17, 100.0, date(2018, 2, 1))],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            _row(y17, 101.0, date(2019, 2, 1)), _row(y18, 120.0, date(2019, 2, 1))],
    }
    out = resolve_concept("revenue", rows)
    by_end = {r["period_end"]: r for r in out}
    # the better-ranked tag wins the overlapping period, and 2018 is still there
    assert by_end[date(2017, 12, 31)]["source_tag"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert by_end[date(2018, 12, 31)]["value"] == 120.0
    assert all(r["concept"] == "revenue" for r in out)


def test_resolve_keeps_restated_rows_for_the_date_gate():
    p = (date(2019, 1, 1), date(2019, 12, 31))
    rows = {"Revenues": [_row(p, 100.0, date(2020, 2, 1), "orig"), _row(p, 95.0, date(2021, 2, 1), "restated")]}
    out = resolve_concept("revenue", rows)
    assert {r["accession"] for r in out} == {"orig", "restated"}


def test_resolve_ignores_tags_that_are_not_in_the_concept():
    p = (date(2019, 1, 1), date(2019, 12, 31))
    assert resolve_concept("revenue", {"NotATag": [_row(p, 1.0, date(2020, 1, 1))]}) == []
