import json
from datetime import date

import pytest

from ingest import events as ev
from ingest.concepts import Concept
from ingest.__main__ import main
from ingest.load import Dataset, load, read_jsonl, write_jsonl
from ingest.macro import FredClient, MacroSkipped, StooqClient, parse_alfred, parse_stooq
from ingest.parse import parse_companyfacts
from ingest.qa import format_report, qa_report
from ingest.sec import SecClient
from ingest.tests import fixtures as fx

UA = "Jane Doe jane@firm.com"
D = date.fromisoformat


def sec_client(tmp_path, net=None, **kw):
    return SecClient(user_agent=UA, cache_dir=tmp_path / "sec", opener=net or fx.FakeNet(fx.sec_routes()),
                     sleep=lambda s: None, **kw)


# ---- parser -------------------------------------------------------------------------------------

def rows(concept="revenue"):
    return [r for r in parse_companyfacts("anon_001", fx.companyfacts()) if r["concept"] == concept]


def test_rows_match_schema_and_carry_filed_date():
    from schemas import Fact
    allrows = parse_companyfacts("anon_001", fx.companyfacts())
    assert allrows
    for r in allrows:
        assert isinstance(r["filed_date"], date)
        # schemas.Fact (extra=forbid) predates source_tag/fiscal_year: request to A, see contract test
        Fact(**{k: v for k, v in r.items() if k not in ("source_tag", "fiscal_year")})


def test_restatement_is_a_new_row_and_repeat_is_dropped():
    fy19 = [r for r in rows() if r["period_end"] == D("2019-12-31")]
    assert [(r["value"], r["filed_date"]) for r in fy19] == [(1000.0, D("2020-02-20")), (1100.0, D("2021-02-18"))]
    assert {r["accession"] for r in fy19} == {"0001-20-000001", "0001-21-000001"}


def test_non_periodic_forms_excluded_and_fallback_fills_only_gaps():
    rs = rows()
    assert all(r["form"] in ("10-K", "10-Q") for r in rs)
    fy18 = [r for r in rs if r["period_end"] == D("2018-12-31")]
    assert [r["value"] for r in fy18] == [800.0]                      # fallback filled the gap
    assert 999.0 not in {r["value"] for r in rs}                      # but did not override the primary tag


def test_custom_concept_map_and_missing_tags():
    out = parse_companyfacts("c", fx.companyfacts(), {"assets": Concept(("Assets",), "USD"),
                                                       "nothing": Concept(("Nope",), "USD")})
    assert {r["concept"] for r in out} == {"assets"}


def test_as_of_leakage_property_through_store_gate(tmp_path):
    """Rows loaded by ingest, queried through store.queries: nothing filed after as_of is visible."""
    import store.queries as q
    ds = load(["ACME"], sec_client(tmp_path), universe_file=None)
    old = q._backend
    try:
        q.set_backend(ds.backend())
        for as_of in (D("2020-01-01"), D("2020-06-01"), D("2021-02-17"), D("2021-02-18"), D("2030-01-01")):
            for f in q.get_facts("anon_001", "revenue", as_of):
                assert f.filed_date <= as_of
            for e in q.get_events("anon_001", as_of):
                assert e.filed_date <= as_of
        before = {f.period_end: f.value for f in q.get_facts("anon_001", "revenue", D("2021-02-17"))}
        after = {f.period_end: f.value for f in q.get_facts("anon_001", "revenue", D("2021-02-18"))}
        assert before[D("2019-12-31")] == 1000.0      # restatement invisible before its filing date
        assert after[D("2019-12-31")] == 1100.0
        assert q.get_facts("anon_001", "revenue", D("2018-01-01")) == []
        assert [e.items for e in q.get_events("anon_001", D("2020-12-31"), forms=["8-K"])] == [
            ["5.02"], ["2.02"], ["4.01", "9.01"]]
    finally:
        q.set_backend(old)


# ---- events -------------------------------------------------------------------------------------

def test_extract_events_item_codes_and_forms():
    from ingest.sec import SecClient  # noqa: F401
    filings = [dict(zip(fx.submissions()["filings"]["recent"], v)) for v in
               zip(*fx.submissions()["filings"]["recent"].values())]
    out = ev.extract_events("anon_001", filings, cik=fx.CIK)
    assert [e["form"] for e in out] == ["8-K", "8-K", "10-K"]          # SC 13G dropped, sorted by filing
    assert out[1]["items"] == ["4.01", "9.01"] and out[0]["items"] == ["2.02"]
    assert out[2]["items"] == [] and out[2]["text_ref"] == "1234567/000121000001/a10k.htm"
    assert all(isinstance(e["filed_date"], date) for e in out)


def test_going_concern_detection():
    yes = "<p>These conditions raise <b>substantial doubt</b> about the Company's ability to continue as a going concern.</p>"
    no = "Management's plans alleviate substantial doubt about our ability to continue as a going concern."
    assert ev.detect_going_concern(yes)
    assert ev.detect_going_concern("Nothing to see here, revenue grew.") == []
    assert ev.detect_going_concern(no) == []
    events = [{"form": "10-K", "items": [], "text_ref": "a"}, {"form": "8-K", "items": [], "text_ref": "b"},
              {"form": "10-K", "items": [], "text_ref": "c"}]
    n = ev.tag_going_concern(events, lambda e: yes if e["text_ref"] in "ab" else None)
    assert n == 1 and [e.get("going_concern_hits", 0) for e in events] == [1, 0, 0]
    assert all(e["items"] == [] for e in events)


# ---- macro / prices -----------------------------------------------------------------------------

def test_alfred_vintages_and_missing_values():
    pts = parse_alfred("CPI", fx.alfred())
    assert [(p["obs_date"], p["value"], p["vintage_date"]) for p in pts] == [
        (D("2020-01-01"), 100.0, D("2020-02-15")), (D("2020-01-01"), 101.5, D("2020-03-15"))]


def test_fred_cache_and_skip_without_key(tmp_path):
    with pytest.raises(MacroSkipped):
        FredClient(api_key="", cache_dir=tmp_path).series("CPI")
    net = fx.FakeNet({"stlouisfed": fx.alfred()})
    FredClient(api_key="SECRETKEY123", cache_dir=tmp_path, opener=net).series("CPI", vintaged=True)
    assert len(net.calls) == 1
    cached = FredClient(api_key="", cache_dir=tmp_path, offline=True).series("CPI", vintaged=True)  # no key, no network
    assert len(cached) == 2
    assert "SECRETKEY123" not in " ".join(str(p) for p in tmp_path.rglob("*"))  # api key never in a path


def test_stooq(tmp_path):
    assert parse_stooq("No data") == []
    net = fx.FakeNet({"stooq": fx.STOOQ.encode()})
    c = StooqClient(cache_dir=tmp_path, opener=net)
    assert [p["close"] for p in c.prices("ACME")] == [1.5, 1.7]
    StooqClient(cache_dir=tmp_path, offline=True).prices("ACME")
    assert len(net.calls) == 1


def test_macro_vintage_gate(tmp_path):
    import store.queries as q
    ds = Dataset(macro=parse_alfred("CPI", fx.alfred()))
    old = q._backend
    try:
        q.set_backend(ds.backend())
        assert q.get_macro("CPI", D("2020-03-01"))[0].value == 100.0
        assert q.get_macro("CPI", D("2020-03-15"))[0].value == 101.5
        assert q.get_macro("CPI", D("2020-02-01")) == []
    finally:
        q.set_backend(old)


# ---- loader, offline re-run, QA, CLI ------------------------------------------------------------

def test_load_then_rerun_offline_from_cache_identical(tmp_path):
    net = fx.FakeNet(fx.sec_routes())
    sec = sec_client(tmp_path, net)
    first = load(["ACME"], sec, universe_file=None)
    assert net.calls and sec.fetches == 4   # tickers, facts, submissions, older page
    offline = SecClient(cache_dir=tmp_path / "sec", offline=True, opener=lambda *a, **k: 1 / 0)
    second = load(["ACME"], offline, universe_file=None)
    assert offline.fetches == 0 and second.facts == first.facts and second.events == first.events
    assert first.companies[0] == {"company_id": "anon_001", "cik": "0001234567", "ticker": "ACME",
                                  "name": "Acme Corp", "sector": None, "covid_group": None,
                                  "held_out": False, "short_history": False, "sic": None}
    assert any(e["items"] == ["5.02"] for e in first.events)  # older submissions page joined


def test_unknown_ticker_and_missing_cache_are_gaps_not_crashes(tmp_path):
    sec = sec_client(tmp_path)
    ds = load(["ACME", "ZZZZ"], sec, universe_file=None)
    assert "ZZZZ" not in [c["ticker"] for c in ds.companies if c["cik"]]
    assert ds.gaps["anon_002"]
    cold = SecClient(cache_dir=tmp_path / "empty", offline=True)
    # tickers file missing entirely is a hard stop (nothing to resolve); that is a CacheMiss
    from ingest.sec import CacheMiss
    with pytest.raises(CacheMiss):
        load(["ACME"], cold, universe_file=None)


def test_universe_file_supplies_ids_and_sector(tmp_path):
    u = tmp_path / "universe.json"
    u.write_text(json.dumps([{"ticker": "ACME", "company_id": "anon_042", "sector": "Industrials"}]))
    ds = load(["ACME"], sec_client(tmp_path), universe_file=u)
    assert ds.companies[0]["company_id"] == "anon_042" and ds.companies[0]["sector"] == "Industrials"
    assert {f["company_id"] for f in ds.facts} == {"anon_042"}


def test_jsonl_roundtrip_and_qa(tmp_path):
    ds = load(["ACME"], sec_client(tmp_path), fred=FredClient(api_key="k", cache_dir=tmp_path / "f",
              opener=fx.FakeNet({"stlouisfed": fx.alfred()})), series=["CPI"], universe_file=None)
    out = write_jsonl(ds, tmp_path / "out")
    back = read_jsonl(out)
    assert back.facts == ds.facts and back.events == ds.events and back.macro == ds.macro
    rep = qa_report(back)
    p = rep["companies"]["anon_001"]
    assert p["facts"] == len(ds.facts) and p["restated_periods"] == 1 and p["eight_k"] == 3
    assert "revenue" not in p["missing_concepts"] and "net_income" in p["missing_concepts"]
    assert rep["macro_series"] == ["CPI"]
    assert "anon_001" in format_report(rep)


def test_cli_load_offline_rerun(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SEC_USER_AGENT", UA)
    sec = sec_client(tmp_path)
    load(["ACME"], sec, universe_file=None)  # warm the cache
    import ingest.__main__ as m
    monkeypatch.setattr(m, "SecClient", lambda **kw: SecClient(cache_dir=tmp_path / "sec", **kw))
    rc = main(["load", "--tickers", "ACME", "--offline", "--out", str(tmp_path / "o")])
    out = capsys.readouterr().out
    assert "anon_051" in out and "network fetches: 0" in out  # not in the universe: next free id
    assert rc == 1  # most concepts missing in the tiny fixture -> flagged as a gap
    assert (tmp_path / "o" / "facts.jsonl").is_file()
    assert main(["report", "--in", str(tmp_path / "o")]) == 0


def test_raw_cache_dir_env_moves_both_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_CACHE_DIR", str(tmp_path / "elsewhere"))
    assert SecClient(offline=True).dir == tmp_path / "elsewhere" / "sec"
    assert FredClient(offline=True).dir == tmp_path / "elsewhere"
    monkeypatch.delenv("RAW_CACHE_DIR")
    assert SecClient(offline=True).dir.parts[-2:] == ("raw", "sec")


def test_cli_full_reload_from_raw_dir_with_the_network_cut_writes_the_qa_report(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw"
    load(["ACME"], SecClient(user_agent=UA, cache_dir=raw / "sec", opener=fx.FakeNet(fx.sec_routes()),
                             sleep=lambda s: None), universe_file=None)          # warm the SEC cache
    (raw / "fred").mkdir()
    (raw / "fred" / "CPI.json").write_text(json.dumps(fx.alfred()))
    import urllib.request

    def no_network(*a, **k):
        raise AssertionError("the offline reload touched the network")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    out = tmp_path / "o"
    main(["load", "--tickers", "ACME", "--offline", "--raw-dir", str(raw), "--fred", "--series", "CPI",
          "--out", str(out)])
    assert "network fetches: 0" in capsys.readouterr().out
    report = (out / "qa_report.txt").read_text()
    assert report.startswith("Ingest QA:") and "network fetches: 0" in report and "macro series: CPI" in report
    assert json.loads((out / "qa_report.json").read_text())["totals"]["companies"] == 1
    assert read_jsonl(out).macro and read_jsonl(out).facts
