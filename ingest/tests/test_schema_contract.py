"""Ingest output vs the FINAL store/schema.sql, A's concept map and metrics/SPEC.md (all offline)."""
import json
import re
from datetime import date

from ingest import concepts as ic
from ingest.load import (COLUMNS, SCHEMA_FILE, UNIVERSE_FILE, Dataset, load, read_universe,
                         write_postgres, write_runs_companies)
from ingest.macro import FredClient, parse_alfred
from ingest.parse import parse_companyfacts
from ingest.tests import fixtures as fx
from ingest.tests.test_ingest import UA, sec_client  # noqa: F401
from store.concepts import CONCEPTS, resolve_concept

GENERATED = {"id", "period_start_key"}


def sql_columns(table: str) -> list[str]:
    sql = SCHEMA_FILE.read_text()
    body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", sql, re.S).group(1)
    cols = [m.group(1) for line in body.splitlines()
            if (m := re.match(r"\s+([a-z_]+)\s+[A-Z]", line)) and m.group(1) not in ("UNIQUE", "PRIMARY")]
    extra = re.findall(rf"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS (\w+)", sql)
    return [c for c in cols + extra if c not in GENERATED]


def test_columns_constant_equals_schema_sql():
    for t, cols in COLUMNS.items():
        assert set(cols) == set(sql_columns(t)), t


def test_row_keys_match_sql_columns_exactly(tmp_path):
    ds = load(["ACME"], sec_client(tmp_path), fred=FredClient(api_key="k", cache_dir=tmp_path / "f",
              opener=fx.FakeNet({"stlouisfed": fx.alfred()})), series=["GDPC1"],
              stooq=None, universe_file=None)
    ds.prices.append({"company_id": "anon_001", "date": date(2020, 1, 2), "close": 1.5})
    for t in COLUMNS:
        rows = getattr(ds, t)
        assert rows, t
        for r in rows:
            assert set(r) == set(sql_columns(t)), (t, set(r) ^ set(sql_columns(t)))


def test_parser_matches_a_resolve_concept_for_default_map():
    data = fx.companyfacts()
    rows = parse_companyfacts("c", data)
    rev = [r for r in rows if r["concept"] == "revenue"]
    by_tag = {}
    for r in rev:
        by_tag.setdefault(r["source_tag"], []).append(r)
    # feed A's resolver every tag's rows: it must keep exactly what we kept
    again = resolve_concept("revenue", by_tag)
    assert {(r["period_end"], r["accession"], r["source_tag"]) for r in again} == \
           {(r["period_end"], r["accession"], r["source_tag"]) for r in rev}
    assert {r["source_tag"] for r in rev} == {"Revenues", "SalesRevenueNet"}


def test_default_concept_map_is_a_map_and_gaps_empty():
    assert ic.CONCEPT_MAP is CONCEPTS
    assert ic.coverage_gaps() == {"concepts": [], "macro": []}
    # every concept a metric reads is fetched, with the unit A declared
    assert ic.needed_concepts() <= set(ic.CONCEPT_MAP)
    assert ic.needed_macro_series() == {"GDPC1", "UNRATE", "T10Y2Y", "BAA10Y"} == set(ic.MACRO_SERIES_IDS)


def test_unit_and_cumulative_concepts_parse_with_their_declared_unit():
    data = {"facts": {"us-gaap": {"CommonStockDividendsPerShareDeclared": {"units": {"USD/shares": [
        fx.entry(0.5, "2020-03-31", "2020-05-01", "a-1", form="10-Q", start="2020-01-01", fp="Q1")]}}}}}
    (r,) = parse_companyfacts("c", data)
    assert (r["concept"], r["unit"], r["fiscal_year"], r["source_tag"]) == (
        "dividends_per_share", "USD/shares", 2020, "CommonStockDividendsPerShareDeclared")


def test_market_series_get_vintage_equal_obs_date():
    rows = parse_alfred("T10Y2Y", fx.alfred(), vintaged=False)
    assert [(r["obs_date"], r["value"], r["vintage_date"]) for r in rows] == [
        (date(2020, 1, 1), 101.5, date(2020, 1, 1))]  # final value, vintage = obs
    assert len(parse_alfred("GDPC1", fx.alfred())) == 2
    assert set(ic.VINTAGED_SERIES) == {"GDPC1", "UNRATE"}


# ---- universe -----------------------------------------------------------------------------------

def test_default_universe_supplies_anon_ids_sector_heldout(tmp_path):
    u = read_universe(UNIVERSE_FILE)
    nue = next(c for c in u if c["ticker"] == "NUE")
    routes = fx.sec_routes()
    routes["company_tickers.json"] = {"0": {"cik_str": fx.CIK, "ticker": "NUE", "title": "NUCOR CORP"}}
    sec = sec_client(tmp_path, fx.FakeNet(routes))
    ds = load(["nue"], sec)  # default universe file
    (c,) = ds.companies
    assert c["company_id"] == nue["company_id"] and c["sector"] == "Materials"
    assert c["held_out"] is nue["held_out"] and c["covid_group"] == nue["covid_group"]
    assert c["name"] == "Nucor" and c["cik"] == "0001234567"
    assert {f["company_id"] for f in ds.facts} == {nue["company_id"]}


def test_no_tickers_means_whole_universe_and_unknown_ticker_gets_free_id(tmp_path):
    sec = sec_client(tmp_path)
    ds = load(None, sec)  # nothing resolves in the fixture tickers file: every company is a gap
    assert len(ds.companies) == 50 and len(ds.gaps) == 50
    ds2 = load(["ACME"], sec_client(tmp_path))
    assert ds2.companies[0]["company_id"] == "anon_051" and ds2.companies[0]["held_out"] is False


# ---- postgres + runs companies ------------------------------------------------------------------

class FakeCursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append(("execute", sql, params))

    def executemany(self, sql, rows):
        self.log.append(("many", sql, list(rows)))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn(FakeCursor):
    def cursor(self):
        return FakeCursor(self.log)


def test_write_postgres_with_fake_connection(tmp_path):
    ds = load(["ACME"], sec_client(tmp_path), universe_file=None)
    ds.companies.append({"company_id": "anon_099", "cik": None, "ticker": "ZZ", "name": "ZZ", "sector": None,
                         "covid_group": None, "held_out": False, "sic": None})
    ds.facts.append({**ds.facts[0], "company_id": "anon_099"})  # must be skipped: company has no cik
    log, urls = [], []

    def connect(url):
        urls.append(url)
        return FakeConn(log)

    counts = write_postgres(ds, "postgresql://x", connect=connect)
    assert urls == ["postgresql://x"]
    assert log[0][0] == "execute" and "CREATE TABLE IF NOT EXISTS companies" in log[0][1]
    many = {re.search(r"INSERT INTO (\w+)", sql).group(1): (sql, rows) for k, sql, rows in log if k == "many"}
    assert counts["companies"] == 1 and counts["facts"] == len(ds.facts) - 1
    sql, rows = many["facts"]
    assert "ON CONFLICT (company_id, concept, unit, period_start_key, period_end, accession) DO NOTHING" in sql
    assert all(r[0] == "anon_001" and len(r) == len(COLUMNS["facts"]) for r in rows)
    assert "held_out" in many["companies"][0] and len(many["companies"][1][0]) == len(COLUMNS["companies"])
    ev_cols = re.search(r"\((.*?)\) VALUES", many["events"][0]).group(1).split(",")
    assert ev_cols == list(COLUMNS["events"]) and isinstance(many["events"][1][0][2], list)
    assert "macro" not in many and "prices" not in many  # empty tables send nothing
    assert not any("DELETE" in str(e[1]) for e in log)


def test_runs_companies_jsonl_is_dashboard_compatible_and_anonymous(tmp_path):
    ds = load(["ACME"], sec_client(tmp_path), universe_file=None)
    ds.companies[0]["sector"] = "Industrials"
    p = write_runs_companies(ds, tmp_path / "runs")
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    assert rows == [{"company_id": "anon_001", "sector": "Industrials", "covid_group": None, "held_out": False}]
    from dashboard.data import _load_companies
    df = _load_companies(str(tmp_path / "runs"))
    assert df.to_dict("records") == [{"company_id": "anon_001", "sector": "Industrials"}]
    assert "ACME" not in p.read_text() and "Acme" not in p.read_text()
