import json
from datetime import date
from pathlib import Path

from ingest.parse_facts import parse_companyfacts
from ingest.parse_fred import parse_fred
from ingest.parse_submissions import filing_url, parse_submissions

FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text())


# ---------------------------------------------------------------- companyfacts
def _facts():
    return parse_companyfacts(_load("companyfacts_sample.json"), "anon_007")


def test_only_10k_and_10q_forms_become_facts():
    assert {r["form"] for r in _facts()} <= {"10-K", "10-Q"}
    assert not [r for r in _facts() if r["value"] == 999.0]  # the 8-K row


def test_only_the_expected_unit_is_kept_and_unknown_tags_are_ignored():
    rows = _facts()
    assert all(r["unit"] == "USD" for r in rows)
    assert {r["concept"] for r in rows} == {"revenue", "operating_income", "op_cash_flow", "current_assets"}
    assert not any(r["source_tag"] == "SomethingTheMapDoesNotKnow" for r in rows)


def test_a_duration_fact_with_no_start_date_is_dropped():
    # the fixture's PaymentsOfDividends row has an end date but no start: it cannot be placed in a quarter
    assert not [r for r in _facts() if r["concept"] == "dividends_paid"]


def test_three_and_six_month_durations_are_both_kept():
    op = [r for r in _facts() if r["concept"] == "operating_income"]
    assert {(r["period_start"], r["value"]) for r in op} == {(date(2018, 4, 1), 40.0), (date(2018, 1, 1), 75.0)}


def test_cash_flow_year_to_date_is_kept_as_reported():
    cf = {(r["period_start"], r["period_end"]): r["value"] for r in _facts() if r["concept"] == "op_cash_flow"}
    assert cf == {(date(2018, 1, 1), date(2018, 3, 31)): 50.0, (date(2018, 1, 1), date(2018, 6, 30)): 120.0}


def test_balance_sheet_facts_have_no_period_start():
    ca = [r for r in _facts() if r["concept"] == "current_assets"]
    assert len(ca) == 1 and ca[0]["period_start"] is None and ca[0]["period_end"] == date(2018, 6, 30)


def test_the_restated_value_under_a_new_tag_is_a_second_row_for_the_same_period():
    rev = [r for r in _facts() if r["concept"] == "revenue" and r["period_end"] == date(2017, 12, 31)]
    assert {(r["accession"], r["value"], r["source_tag"]) for r in rev} == {
        ("0000000001-18-000010", 1000.0, "Revenues"),
        ("0000000001-19-000020", 1010.0, "RevenueFromContractWithCustomerExcludingAssessedTax")}


def test_rows_carry_filing_dates_and_no_row_is_duplicated():
    rows = _facts()
    assert all(isinstance(r["filed_date"], date) for r in rows)
    idents = [(r["concept"], r["unit"], r["period_start"], r["period_end"], r["accession"]) for r in rows]
    assert len(idents) == len(set(idents))


# ---------------------------------------------------------------- submissions
def test_submissions_events_items_and_sic():
    sub = parse_submissions(_load("submissions_sample.json"), "anon_007")
    assert sub.sic == "3571"
    by_acc = {e["accession"]: e for e in sub.events}
    assert len(sub.events) == 4 and "0000000001-19-000033" not in by_acc  # form 4 is not an event
    assert by_acc["0000000001-19-000031"]["items"] == ["4.01", "9.01"]   # auditor change
    assert by_acc["0000000001-19-000032"]["items"] == ["2.02"]
    assert by_acc["0000000001-19-000020"]["items"] == [] and by_acc["0000000001-19-000020"]["text_ref"].endswith("a10k.htm")
    assert by_acc["0000000001-19-000031"]["text_ref"] is None
    assert sub.extra_files == ["CIK0001234567-submissions-001.json"]


def test_filing_url():
    assert filing_url("0000320193", "0000320193-18-000070", "a10k.htm") == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019318000070/a10k.htm")


# ---------------------------------------------------------------- FRED
def test_revised_series_keeps_every_vintage_and_skips_missing_values():
    rows = parse_fred(_load("fred_gdp_sample.json"), "GDPC1")
    assert [(r["obs_date"], r["vintage_date"], r["value"]) for r in rows] == [
        (date(2019, 1, 1), date(2019, 4, 26), 18927.3), (date(2019, 1, 1), date(2019, 5, 30), 18950.3)]


def test_market_series_vintage_is_the_observation_date():
    rows = parse_fred(_load("fred_t10y2y_sample.json"), "T10Y2Y")
    assert [(r["obs_date"], r["vintage_date"]) for r in rows] == [(date(2019, 3, 22), date(2019, 3, 22))]
