"""Research: lookup, market parsing, plan sentences, and the report built from a synthetic company (known numbers)."""
import json
from datetime import date

import pytest

from metrics.tests import factory as F
from research import market, resolve, text
from research.report import build_report
from research.resolve import Candidate

AFTER = date(2019, 3, 1)       # after the FY2018 10-K: the last quarter is 2018Q4 (i = 23)


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


# ---- lookup --------------------------------------------------------------------------------------------------
LISTINGS = [Candidate(1, "Tesla, Inc.", "TSLA", "Nasdaq"), Candidate(2, "Alphabet Inc.", "GOOGL", "Nasdaq"),
            Candidate(2, "Alphabet Inc.", "GOOG", "Nasdaq"), Candidate(3, "Apple Inc.", "AAPL", "Nasdaq"),
            Candidate(4, "Tesla Motors Fund", "TSLX", "OTC"), Candidate(5, "Berkshire Hathaway Inc.", "BRK-B", "NYSE")]


def test_search_ranks_exact_ticker_first_then_names_and_lists_a_company_once():
    assert [c.ticker for c in resolve.search("tsla", LISTINGS)] == ["TSLA"]
    assert resolve.search("tesla", LISTINGS)[0].ticker == "TSLA"
    assert len(resolve.search("alphabet", LISTINGS)) == 1
    assert resolve.search("nonexistent plc", LISTINGS) == [] and resolve.search("  ", LISTINGS) == []


def test_load_listings_reads_the_sec_exchange_file():
    class Sec:
        def get_json(self, url):
            return {"fields": ["cik", "name", "ticker", "exchange"], "data": [[1318605, "Tesla, Inc.", "tsla", "Nasdaq"]]}
    assert resolve.load_listings(Sec())[0] == Candidate(1318605, "Tesla, Inc.", "TSLA", "Nasdaq")


# ---- market --------------------------------------------------------------------------------------------------
def test_chart_is_parsed_and_bad_data_returns_none():
    raw = {"chart": {"result": [{"meta": {"regularMarketPrice": 10.5, "currency": "USD", "regularMarketTime": 1700000000,
                                          "fiftyTwoWeekHigh": 12, "fiftyTwoWeekLow": 8},
                                 "timestamp": [1690000000, 1700000000],
                                 "indicators": {"quote": [{"close": [9.0, None]}]}}]}}
    q = market.parse_chart(raw, "X")
    assert q.price == 10.5 and q.high_52w == 12 and len(q.history) == 1
    assert market.parse_chart({"chart": {"result": None}}, "X") is None


def test_share_classes_in_one_filing_are_added_together_and_the_newest_filing_wins():
    rows = [{"end": "2026-07-01", "filed": "2026-07-20", "value": 6.0, "accession": "B"},
            {"end": "2026-07-01", "filed": "2026-07-20", "value": 1.0, "accession": "B"},
            {"end": "2026-04-01", "filed": "2026-04-20", "value": 99.0, "accession": "A"}]
    assert market.shares_outstanding(rows) == (7.0, "2026-07-01", "B")
    assert market.shares_outstanding([]) is None


# ---- plan sentences -----------------------------------------------------------------------------------------
DOC = ("ITEM 1. BUSINESS We design and sell electric vehicles and energy storage systems to customers worldwide every year. "
       "We plan to expand our manufacturing capacity to additional countries over the coming years to meet demand. "
       "We may not be able to expand capacity if demand falls, which could adversely affect our results of operations. "
       "We continue to invest in research and development of new battery technology to lower the cost of our products. "
       "We currently expect our capital expenditures to rise next year because of new factories and compute capacity. "
       "These forward-looking statements involve risks and uncertainties and actual results may differ from them materially.")


def test_candidates_keep_declarative_plan_sentences_and_drop_risk_factors_and_boilerplate():
    c = text.candidates(DOC)
    assert any("plan to expand our manufacturing" in s for s in c["strategy"])
    assert not any("may not be able" in s for s in c["strategy"])
    assert any("research and development" in s for s in c["rnd"])
    assert any("capital expenditures" in s for s in c["outlook"])
    assert not any("forward-looking" in s for v in c.values() for s in v)


class _Gw:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, agent, messages, **kw):
        return self.reply


def test_a_chooser_can_only_pick_sentences_that_were_offered_and_a_failure_falls_back():
    about, strategy, rnd, outlook = text.extract(DOC, _Gw('{"about": 1, "strategy": [2, 99], "rnd": [], "outlook": [3]}'))
    assert about and all(s in DOC for s in [about, *strategy, *outlook]) and len(strategy) <= 1   # 99 was never offered
    fallback = text.extract(DOC, _Gw("not json"))
    assert fallback[1] and all(s in DOC for s in fallback[1])


def test_the_latest_10k_is_chosen():
    f = [{"form": "10-K", "filingDate": "2024-02-01", "primaryDocument": "a.htm", "accessionNumber": "a"},
         {"form": "10-Q", "filingDate": "2025-05-01", "primaryDocument": "q.htm", "accessionNumber": "q"},
         {"form": "10-K", "filingDate": "2025-02-01", "primaryDocument": "b.htm", "accessionNumber": "b"}]
    assert text.latest_10k(f)["accessionNumber"] == "b"


# ---- the report ----------------------------------------------------------------------------------------------
rev = lambda i: 100 + 10 * i                      # noqa: E731
opi = lambda i: 20 + i                            # noqa: E731
ttm = lambda f, i: sum(f(j) for j in range(i - 3, i + 1))   # noqa: E731
PROFILE = {"name": "Synthetic Co", "ticker": "SYN", "exchange": "Nasdaq", "market": "US", "cik": 1}


def _fig(report, key):
    return next(f for s in report["sections"] for f in s["figures"] if f["key"] == key)


def test_report_figures_match_hand_computed_values():
    F.install(F.build_facts())
    r = build_report("anon_001", AFTER, PROFILE)
    assert r["supported"] and r["data_through"] == "2018-12-31"
    R = ttm(rev, 23)
    assert _fig(r, "revenue")["value"] == pytest.approx(R)
    assert _fig(r, "revenue_growth")["value"] == pytest.approx(R / ttm(rev, 19) - 1)
    assert _fig(r, "operating_margin")["value"] == pytest.approx(ttm(opi, 23) / R)
    assert _fig(r, "ebitda")["value"] == pytest.approx(ttm(opi, 23) + 20)          # D&A is 5 a quarter
    assert _fig(r, "fcf")["value"] == pytest.approx(ttm(lambda i: 30 + 3 * i, 23) - 40)
    assert _fig(r, "net_debt")["value"] == pytest.approx(120 - 50)                  # debt 100 + 20, cash 50
    assert _fig(r, "current_ratio")["value"] == pytest.approx((200 + 23) / 100)


def test_every_figure_names_its_filings_and_has_year_spaced_history():
    F.install(F.build_facts())
    r = build_report("anon_001", AFTER, PROFILE)
    rev_fig = _fig(r, "revenue")
    assert rev_fig["sources"] and all(s.startswith("ACC-") for s in rev_fig["sources"])
    assert [h["end"] for h in rev_fig["history"]][-1] == "2018-12-31" and len(rev_fig["history"]) >= 5


def test_the_report_cannot_see_filings_after_its_date():
    F.install(F.build_facts())
    before = build_report("anon_001", date(2019, 2, 19), PROFILE)               # before the FY2018 10-K
    assert before["data_through"] == "2018-09-30"


def test_untagged_operating_income_is_approximated_and_says_so():
    F.install(F.build_facts(operating_income=None, costs_and_expenses=lambda i: rev(i) - opi(i)))
    r = build_report("anon_001", AFTER, PROFILE)
    assert _fig(r, "operating_margin")["approx"] is True
    assert _fig(r, "operating_margin")["value"] == pytest.approx(ttm(opi, 23) / ttm(rev, 23))
    assert any("does not report operating income" in n for n in r["notes"])


def test_a_company_with_no_revenue_filings_is_reported_as_unsupported_not_guessed():
    F.install([])
    r = build_report("anon_001", AFTER, PROFILE)
    assert r["supported"] is False and "20-F" in r["reason"]


def test_market_value_and_multiples_use_the_figures_in_the_report():
    F.install(F.build_facts())
    q = market.Quote("SYN", 10.0, "USD", "2019-02-28", 12.0, 8.0, [])
    r = build_report("anon_001", AFTER, PROFILE, quote=q, shares=(1000.0, "2019-02-01", "SH"))
    m = r["market"]
    assert m["market_cap"] == 10_000.0 and m["enterprise_value"] == pytest.approx(10_000 + 70)
    assert m["price_to_sales"] == pytest.approx(10_000 / ttm(rev, 23))
    assert build_report("anon_001", AFTER, PROFILE)["market"] is None


def test_report_is_json_serialisable():
    F.install(F.build_facts())
    json.dumps(build_report("anon_001", AFTER, PROFILE))
