"""A restatement filed under a DIFFERENT tag must survive parsing (found while merging A and B)."""
from datetime import date

from ingest.parse import parse_companyfacts


def _facts():
    year = {"start": "2017-01-01", "end": "2017-12-31", "fy": 2017, "fp": "FY", "form": "10-K"}
    return {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{**year, "val": 1000, "accn": "0000000001-18-000010", "filed": "2018-02-15"}]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {**year, "val": 1010, "accn": "0000000001-19-000020", "filed": "2019-02-14"}]}},
    }}}


def test_old_and_restated_values_under_different_tags_are_both_kept():
    rows = [r for r in parse_companyfacts("anon_001", _facts()) if r["concept"] == "revenue"]
    assert {(r["accession"], r["value"], r["source_tag"]) for r in rows} == {
        ("0000000001-18-000010", 1000.0, "Revenues"),
        ("0000000001-19-000020", 1010.0, "RevenueFromContractWithCustomerExcludingAssessedTax")}


def test_the_date_gate_shows_the_old_value_first_and_the_restated_one_after():
    from schemas import Fact
    from store import queries
    from store.queries import InMemoryBackend
    rows = [{k: v for k, v in r.items() if k in Fact.model_fields}
            for r in parse_companyfacts("anon_001", _facts()) if r["concept"] == "revenue"]
    queries.set_backend(InMemoryBackend(facts=rows))
    try:
        assert [f.value for f in queries.get_facts("anon_001", "revenue", date(2019, 2, 13))] == [1000.0]
        assert [f.value for f in queries.get_facts("anon_001", "revenue", date(2019, 2, 14))] == [1010.0]
    finally:
        queries.set_backend(InMemoryBackend())
