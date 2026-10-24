"""Synthetic SEC/FRED/Stooq payloads shaped like the real ones (no network)."""
import json

CIK = 1234567


def entry(val, end, filed, accn, form="10-K", start=None, fp="FY"):
    e = {"end": end, "val": val, "accn": accn, "fy": int(end[:4]), "fp": fp, "form": form, "filed": filed}
    if start:
        e["start"] = start
    return e


def companyfacts():
    rev = [  # FY2019 revenue is restated in the FY2020 10-K (new accession, new value)
        entry(1000, "2019-12-31", "2020-02-20", "0001-20-000001", start="2019-01-01"),
        entry(1100, "2019-12-31", "2021-02-18", "0001-21-000001", start="2019-01-01"),   # restatement
        entry(1100, "2019-12-31", "2022-02-17", "0001-22-000001", start="2019-01-01"),   # mere repeat
        entry(900, "2020-12-31", "2021-02-18", "0001-21-000001", start="2020-01-01"),
        entry(5, "2020-03-31", "2020-05-01", "0001-20-000009", form="10-Q", start="2020-01-01", fp="Q1"),
        entry(7, "2020-03-31", "2020-05-01", "0001-20-000010", form="8-K", start="2020-01-01"),  # not periodic
    ]
    fallback_rev = [  # older tag covers FY2018 only; FY2019 already covered by primary tag
        entry(800, "2018-12-31", "2019-02-21", "0001-19-000001", start="2018-01-01"),
        entry(999, "2019-12-31", "2020-02-20", "0001-20-000001", start="2019-01-01"),
    ]
    return {"cik": CIK, "entityName": "Acme Corp", "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": rev}},
        "SalesRevenueNet": {"units": {"USD": fallback_rev}},
        "Assets": {"units": {"USD": [entry(5000, "2020-12-31", "2021-02-18", "0001-21-000001")]}},
    }}}


def submissions():
    return {"cik": str(CIK), "filings": {"recent": {
        "accessionNumber": ["0001-21-000001", "0001-20-000050", "0001-20-000049", "0001-20-000048"],
        "form": ["10-K", "8-K", "8-K", "SC 13G"],
        "filingDate": ["2021-02-18", "2020-06-01", "2020-04-15", "2020-03-01"],
        "items": ["", "4.01,9.01", "2.02", ""],
        "primaryDocument": ["a10k.htm", "a8k.htm", "b8k.htm", "x.htm"],
    }, "files": [{"name": "CIK0001234567-submissions-001.json"}]}}


def submissions_older():
    return {"accessionNumber": ["0001-18-000007"], "form": ["8-K"], "filingDate": ["2018-05-02"],
            "items": ["5.02"], "primaryDocument": ["old.htm"]}


def tickers():
    return {"0": {"cik_str": CIK, "ticker": "ACME", "title": "Acme Corp"}}


def alfred():
    return {"observations": [
        {"date": "2020-01-01", "value": "100.0", "realtime_start": "2020-02-15", "realtime_end": "2020-03-14"},
        {"date": "2020-01-01", "value": "101.5", "realtime_start": "2020-03-15", "realtime_end": "9999-12-31"},
        {"date": "2020-02-01", "value": ".", "realtime_start": "2020-03-15", "realtime_end": "9999-12-31"},
    ]}


STOOQ = "Date,Open,High,Low,Close,Volume\n2020-01-02,1,2,1,1.5,10\n2020-01-03,1,2,1,1.7,10\n"


class FakeNet:
    """Serves URL -> bytes by substring. Counts calls."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        for key, body in self.routes.items():
            if key in url:
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                return _Resp(data)
        raise AssertionError(f"unexpected url {url}")


class _Resp:
    def __init__(self, b):
        self.b, self.headers = b, {}

    def read(self):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sec_routes():
    return {"company_tickers.json": tickers(), "companyfacts/CIK0001234567": companyfacts(),
            "submissions/CIK0001234567.json": submissions(),
            "submissions/CIK0001234567-submissions-001.json": submissions_older()}
