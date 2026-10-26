"""SEC fetcher: polite, rate-limited, and every raw response is on disk before anything parses it.

Rules it enforces (CLAUDE.md data sources, TASKS.md B1):

* `User-Agent` must carry a name and an email (SEC blocks anonymous clients). Read from
  `SEC_USER_AGENT` in `.env`; a placeholder or an agent with no email is refused.
* Under ~10 requests a second across the whole process (default 8/s), shared by all threads.
* Raw bytes are written to `data/raw/sec/<host>/<path>` first. A cache hit never touches the
  network, so the whole load re-runs offline. `offline=True` makes a miss raise `CacheMiss`.
* Failed responses (404, 5xx, anything non-200) are never cached. 429 and 5xx are retried
  with backoff, honouring `Retry-After`.

    sec = SecClient()
    sec.company_tickers()            # {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
    sec.submissions(320193)          # filing list with form, items, filingDate, accessionNumber
    sec.companyfacts(320193)         # every XBRL fact, each with `filed`, `accn`, `form`
    sec.filing_document(320193, "0000320193-24-000123", "aapl-20240928.htm")

Parsing lives elsewhere. This module only gets bytes in and remembers them.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = ROOT / "data" / "raw" / "sec"
DEFAULT_RATE = 8.0  # requests per second; SEC's limit is 10
MAX_ATTEMPTS = 5

WWW = "https://www.sec.gov"
DATA = "https://data.sec.gov"

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PLACEHOLDER = ("your name", "your.email", "example.com")


class SecError(RuntimeError):
    """The SEC replied with something we can't use. Never cached."""


class NotFound(SecError):
    """404: the URL does not exist (a company with no XBRL, a wrong accession)."""


class CacheMiss(SecError):
    """offline=True and this URL has no saved response."""


def check_user_agent(ua: str | None) -> str:
    """Return a usable User-Agent or raise. SEC wants 'Name email@domain'."""
    ua = (ua or "").strip().strip('"').strip("'")
    if not ua:
        raise SecError("SEC_USER_AGENT is not set. Use a name and email, e.g. 'Jane Doe jane@firm.com'.")
    if not _EMAIL.search(ua) or any(p in ua.lower() for p in _PLACEHOLDER):
        raise SecError("SEC_USER_AGENT needs your real name and email (got a placeholder or no email).")
    return ua


def pad_cik(cik: int | str) -> str:
    """10-digit zero-padded CIK, the form data.sec.gov URLs use."""
    digits = re.sub(r"\D", "", str(cik))
    if not digits:
        raise ValueError(f"not a CIK: {cik!r}")
    return digits.zfill(10)


def _load_env_agent() -> str | None:
    """SEC_USER_AGENT from the environment, falling back to the project .env."""
    if os.environ.get("SEC_USER_AGENT"):
        return os.environ["SEC_USER_AGENT"]
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass
    return os.environ.get("SEC_USER_AGENT")


def raw_root() -> Path:
    """Raw cache root: `RAW_CACHE_DIR` (relative = from the repo root), else data/raw. SEC files go in <root>/sec."""
    env = os.environ.get("RAW_CACHE_DIR")
    if not env:
        return DEFAULT_CACHE_DIR.parent
    p = Path(env).expanduser()
    return p if p.is_absolute() else ROOT / p


class RateLimiter:
    """Spaces calls at least 1/rate seconds apart, safe to share between threads."""

    def __init__(self, rate: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.interval = 1.0 / rate
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self.interval
            delay = start - now
        if delay > 0:
            self._sleep(delay)


class SecClient:
    def __init__(self, user_agent: str | None = None, cache_dir: Path | str | None = None,
                 rate: float = DEFAULT_RATE, offline: bool = False, refresh: bool = False,
                 timeout: float = 30.0, opener: Callable[..., Any] | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        # offline needs no network, so it needs no User-Agent either
        self.user_agent = None if offline and not user_agent else check_user_agent(
            user_agent or _load_env_agent())
        self.dir = Path(cache_dir) if cache_dir else raw_root() / "sec"
        self.offline, self.refresh, self.timeout = offline, refresh, timeout
        self._limiter = RateLimiter(min(rate, 10.0), sleep=sleep)
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self.hits = 0
        self.fetches = 0

    # ---- cache ------------------------------------------------------------

    def path_for(self, url: str) -> Path:
        """Readable on-disk path for a URL: <cache>/<host>/<path>, query folded into a hash."""
        u = urllib.parse.urlsplit(url)
        parts = [re.sub(r"[^A-Za-z0-9._=-]", "_", p) for p in u.path.split("/") if p and p != ".."]
        if not parts:
            parts = ["index"]
        if u.query:
            parts[-1] += "." + hashlib.sha256(u.query.encode()).hexdigest()[:10]
        return self.dir.joinpath(u.netloc, *parts)

    def cached(self, url: str) -> bool:
        return self.path_for(url).is_file()

    def _save(self, path: Path, body: bytes) -> None:
        # write-then-rename so a crash never leaves a half file that later reads as a hit
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp{os.getpid()}.{threading.get_ident()}")
        tmp.write_bytes(body)
        os.replace(tmp, path)

    # ---- fetching ---------------------------------------------------------

    def get(self, url: str) -> bytes:
        """Raw bytes for a URL: from disk if we have them, else fetched once and saved."""
        path = self.path_for(url)
        if not self.refresh and path.is_file():
            self.hits += 1
            return path.read_bytes()
        if self.offline:
            raise CacheMiss(f"offline and not cached: {url}")
        body = self._download(url)
        self._save(path, body)
        self.fetches += 1
        return body

    def _download(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent, "Accept-Encoding": "gzip"})
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._limiter.wait()
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    body = resp.read()
                    if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                        body = gzip.decompress(body)
                    return body
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise NotFound(url) from e
                if e.code not in (429, 500, 502, 503, 504) or attempt == MAX_ATTEMPTS:
                    raise SecError(f"HTTP {e.code} for {url}") from e
                self._sleep(self._retry_delay(e, attempt))
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt == MAX_ATTEMPTS:
                    raise SecError(f"network error for {url}: {e}") from e
                self._sleep(2.0 ** attempt)
        raise SecError(f"gave up on {url}")  # unreachable, keeps type checkers calm

    @staticmethod
    def _retry_delay(err: urllib.error.HTTPError, attempt: int) -> float:
        retry_after = err.headers.get("Retry-After") if err.headers else None
        try:
            return max(float(retry_after), 1.0)
        except (TypeError, ValueError):
            return 2.0 ** attempt

    def get_json(self, url: str) -> Any:
        body = self.get(url)
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            # a bad body is already on disk; drop it so the next run refetches instead of looping
            self.path_for(url).unlink(missing_ok=True)
            raise SecError(f"not JSON from {url}: {e}") from e

    # ---- endpoints --------------------------------------------------------

    def company_tickers(self) -> dict:
        return self.get_json(f"{WWW}/files/company_tickers.json")

    def submissions(self, cik: int | str) -> dict:
        return self.get_json(f"{DATA}/submissions/CIK{pad_cik(cik)}.json")

    def submissions_page(self, name: str) -> dict:
        """An older-filings page named in submissions()['filings']['files'][i]['name']."""
        return self.get_json(f"{DATA}/submissions/{name}")

    def companyfacts(self, cik: int | str) -> dict:
        return self.get_json(f"{DATA}/api/xbrl/companyfacts/CIK{pad_cik(cik)}.json")

    def filing_document(self, cik: int | str, accession: str, filename: str) -> bytes:
        """A filing's primary document (10-K/10-Q/8-K body) from the Archives."""
        return self.get(self.archive_url(cik, accession, filename))

    @staticmethod
    def archive_url(cik: int | str, accession: str, filename: str) -> str:
        return (f"{WWW}/Archives/edgar/data/{int(pad_cik(cik))}/"
                f"{accession.replace('-', '')}/{filename}")

    def all_submission_filings(self, cik: int | str) -> list[dict]:
        """Every filing for a company as row dicts, joining the recent block and older pages."""
        main = self.submissions(cik)
        blocks = [main["filings"]["recent"]]
        blocks += [self.submissions_page(f["name"]) for f in main["filings"].get("files", [])]
        rows: list[dict] = []
        for b in blocks:
            keys = list(b)
            rows += [dict(zip(keys, vals)) for vals in zip(*b.values())]
        return rows
