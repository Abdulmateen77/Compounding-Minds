"""A name or ticker -> the listed company and its market.

Source: the SEC's company_tickers_exchange.json (every US-listed filer, with its exchange). Only US listings
are covered here; London and European listings are a later data source, and a search that finds nothing says so
instead of guessing.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ingest.sec import WWW, SecClient

EXCHANGE_URL = f"{WWW}/files/company_tickers_exchange.json"
MAJOR = {"Nasdaq": 0, "NYSE": 0, "CBOE": 1, "NYSE American": 1, "OTC": 3}
_SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|the|class [a-c]|cl [a-c])\b\.?", re.I)


@dataclass(frozen=True)
class Candidate:
    cik: int
    name: str
    ticker: str
    exchange: str | None
    market: str = "US"

    def as_dict(self) -> dict:
        return asdict(self)


def _norm(s: str) -> str:
    s = _SUFFIX.sub(" ", s.lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def pretty_name(name: str, ticker: str = "") -> str:
    """The SEC lists names in capitals ("COCA COLA CO"). Title-case them; short consonant-only words stay as written
    (HP) and a word that is the ticker (IBM, AMD) stay as written."""
    name = name.strip()
    if not name.isupper():
        return name
    words = []
    for w in name.split():
        core = re.sub(r"[^A-Za-z]", "", w)
        keep = core and (core == ticker.upper() or (not re.search(r"[AEIOUY]", core) and len(core) <= 4))
        words.append(w if keep else w.capitalize())
    return " ".join(words)


def load_listings(sec: SecClient) -> list[Candidate]:
    raw = sec.get_json(EXCHANGE_URL)
    fields = raw["fields"]
    out = []
    for row in raw["data"]:
        d = dict(zip(fields, row))
        out.append(Candidate(int(d["cik"]), pretty_name(str(d["name"]), str(d["ticker"])), str(d["ticker"]).upper(), d.get("exchange")))
    return out


def search(query: str, listings: list[Candidate], limit: int = 8) -> list[Candidate]:
    """Best matches first: exact ticker, exact name, name starts with, name contains. One row per company
    (the share class on the biggest exchange wins), so 'Alphabet' is one result, not two."""
    q = query.strip()
    if not q:
        return []
    qt, qn = q.upper(), _norm(q)
    scored: list[tuple[tuple, Candidate]] = []
    for c in listings:
        n = _norm(c.name)
        if c.ticker == qt:
            rank = 0
        elif qn and n == qn:
            rank = 1
        elif qn and n.startswith(qn):
            rank = 2
        elif qn and qn in n:
            rank = 3
        else:
            continue
        scored.append(((rank, MAJOR.get(c.exchange or "", 4), len(c.ticker), c.ticker), c))
    scored.sort(key=lambda x: x[0])
    seen, out = set(), []
    for _, c in scored:
        if c.cik in seen:
            continue
        seen.add(c.cik)
        out.append(c)
        if len(out) >= limit:
            break
    return out
