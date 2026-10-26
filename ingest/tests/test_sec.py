"""SEC fetcher: cache, rate limit, User-Agent, retries. A fake opener stands in for the network."""
import gzip
import io
import json
import urllib.error

import pytest

from ingest.sec import (CacheMiss, NotFound, RateLimiter, SecClient, SecError,
                        check_user_agent, pad_cik)

UA = "Jane Doe jane@firm.com"


class FakeResp:
    def __init__(self, body: bytes, gz=False):
        self._b = gzip.compress(body) if gz else body
        self.headers = {"Content-Encoding": "gzip"} if gz else {}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, retry_after=None):
    h = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("u", code, "x", h, io.BytesIO(b""))


class Opener:
    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, req, timeout=None):
        self.calls.append(req)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(tmp_path, *script, **kw):
    op = Opener(*script)
    return SecClient(user_agent=UA, cache_dir=tmp_path, opener=op, sleep=lambda s: None, **kw), op


def test_user_agent_needs_name_and_email():
    assert check_user_agent('"Jane Doe jane@firm.com"') == UA
    for bad in (None, "", "Jane Doe", "Your Name your.email@example.com"):
        with pytest.raises(SecError):
            check_user_agent(bad)


def test_request_carries_user_agent(tmp_path):
    c, op = client(tmp_path, FakeResp(b"{}"))
    c.get_json("https://data.sec.gov/submissions/CIK0000320193.json")
    assert op.calls[0].get_header("User-agent") == UA


def test_cache_hit_makes_no_second_request(tmp_path):
    c, op = client(tmp_path, FakeResp(b'{"a":1}'))
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    assert c.get_json(url) == {"a": 1}
    assert c.get_json(url) == {"a": 1}
    assert len(op.calls) == 1 and c.hits == 1 and c.fetches == 1
    assert c.path_for(url).read_bytes() == b'{"a":1}'


def test_offline_replays_from_disk_and_misses_raise(tmp_path):
    c, _ = client(tmp_path, FakeResp(b'{"a":1}'))
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    c.get(url)
    off = SecClient(cache_dir=tmp_path, offline=True)  # no UA, no network
    assert off.get_json(url) == {"a": 1}
    with pytest.raises(CacheMiss):
        off.get("https://data.sec.gov/submissions/CIK0000000001.json")


def test_gzip_is_decompressed_before_caching(tmp_path):
    c, _ = client(tmp_path, FakeResp(b'{"z":1}', gz=True))
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    assert c.get(url) == b'{"z":1}'
    assert c.path_for(url).read_bytes() == b'{"z":1}'


def test_404_and_failures_are_never_cached(tmp_path):
    c, _ = client(tmp_path, http_error(404))
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
    with pytest.raises(NotFound):
        c.get(url)
    assert not c.cached(url)


def test_retries_429_then_succeeds_and_honours_retry_after(tmp_path):
    sleeps = []
    op = Opener(http_error(429, "7"), http_error(503), FakeResp(b"ok"))
    c = SecClient(user_agent=UA, cache_dir=tmp_path, opener=op, sleep=sleeps.append)
    assert c.get("https://www.sec.gov/x.txt") == b"ok"
    assert len(op.calls) == 3 and 7.0 in sleeps


def test_gives_up_after_max_attempts(tmp_path):
    c, op = client(tmp_path, *[http_error(500)] * 5)
    with pytest.raises(SecError):
        c.get("https://www.sec.gov/x.txt")
    assert len(op.calls) == 5


def test_bad_json_is_dropped_from_cache(tmp_path):
    c, _ = client(tmp_path, FakeResp(b"<html>"))
    url = "https://www.sec.gov/files/company_tickers.json"
    with pytest.raises(SecError):
        c.get_json(url)
    assert not c.cached(url)


def test_rate_limiter_spaces_calls():
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        t[0] += s

    rl = RateLimiter(10, clock=lambda: t[0], sleep=sleep)
    for _ in range(11):
        rl.wait()
    assert t[0] == pytest.approx(1.0)  # 11 calls at 10/s: 10 gaps of 0.1s


def test_rate_is_capped_at_ten_per_second(tmp_path):
    c = SecClient(user_agent=UA, cache_dir=tmp_path, rate=50)
    assert c._limiter.interval >= 0.1


def test_urls_and_paths(tmp_path):
    assert pad_cik(320193) == "0000320193"
    assert SecClient.archive_url("0000320193", "0000320193-24-000123", "a.htm") == \
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/a.htm"
    c, _ = client(tmp_path)
    p = c.path_for("https://www.sec.gov/../../etc/passwd?x=1")
    assert tmp_path in p.parents


def test_all_submission_filings_joins_pages(tmp_path):
    main = {"filings": {"recent": {"form": ["10-K"], "items": [""]},
                        "files": [{"name": "CIK0000320193-submissions-001.json"}]}}
    old = {"form": ["8-K"], "items": ["4.01"]}
    c, _ = client(tmp_path, FakeResp(json.dumps(main).encode()), FakeResp(json.dumps(old).encode()))
    rows = c.all_submission_filings(320193)
    assert rows == [{"form": "10-K", "items": ""}, {"form": "8-K", "items": "4.01"}]
