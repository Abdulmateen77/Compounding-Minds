"""Freshness is judged by what a cached file contains, not by when it was saved."""
from research import live


def test_latest_periodic_filing_and_how_current_the_figures_are():
    rows = [{"form": "8-K", "filingDate": "2026-09-01"}, {"form": "10-Q", "filingDate": "2026-07-29", "reportDate": "2026-07-03", "accessionNumber": "b"},
            {"form": "10-K", "filingDate": "2026-02-20", "reportDate": "2025-12-31", "accessionNumber": "a"}]
    assert live.latest_periodic(rows) == {"form": "10-Q", "filed": "2026-07-29", "period": "2026-07-03", "accession": "b"}
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{"filed": "2026-04-30"}, {"filed": "2025-10-20"}]}}}}}
    assert live.facts_filed_through(facts) == "2026-04-30"


class _Sec:
    """A cache that holds April figures and a July filing list; a refetch of the figures returns July figures."""
    offline = False

    def __init__(self):
        self.refresh, self.fetched = False, []

    def get_json(self, url):
        self.fetched.append((url.rsplit("/", 1)[-1], self.refresh))
        if "submissions" in url:
            return {"sic": "2080", "filings": {"recent": {"accessionNumber": ["b"], "filingDate": ["2026-07-29"], "form": ["10-Q"],
                                                          "items": [""], "primaryDocument": ["q.htm"], "reportDate": ["2026-07-03"]}, "files": []}}
        filed = "2026-07-29" if self.refresh else "2026-04-30"
        return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{"start": "2026-04-04", "end": "2026-07-03", "val": 1.0, "accn": "b",
                                                                         "fy": 2026, "fp": "Q2", "form": "10-Q", "filed": filed}]}}}}}

    def path_for(self, url):
        from pathlib import Path
        return Path("does-not-exist")

    def cached(self, url):
        return True


def test_figures_older_than_the_newest_filing_are_downloaded_again():
    live._checked.clear()
    sec = _Sec()
    c = live.load_company(sec, 21344)
    assert c.facts_through == "2026-07-29" and c.latest_filing["filed"] == "2026-07-29"
    assert ("CIK0000021344.json", True) in [f for f in sec.fetched if "CIK" in f[0]]          # refetched with refresh on
