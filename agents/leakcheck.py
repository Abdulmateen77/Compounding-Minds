"""A last line of defence against leaking the answer into a prompt (CLAUDE.md rules 2 and 6).

The agent's user message is built from an anonymous company id, relative-quarter metrics and the
agent's own lessons. None of that should ever contain a company name, a ticker, a calendar year or a
filing accession number (an accession like 0000320193-18-000070 carries the year). The masking code
already scrubs dates; this is the independent check that catches whatever it, a lesson written by an
LLM, or a future change lets through. A prompt that fails is blocked: the model is never called.

Kept deliberately narrow. A false alarm blocks a good call, so it checks only things that can be
matched exactly: years (not decimals), accession numbers, company names as written, and tickers of
two or more letters in capitals (single letters like F and M are ordinary words). Known blind spot:
a company name written all in lower case ("home depot") is not caught.
"""
from __future__ import annotations

import re
from functools import lru_cache

# A year is 19xx or 20xx that is not part of a longer number. Metric values are decimals such as
# 0.2018 or 12.1999, which must not read as years, so a digit or "digit." before it, or a digit or
# ".digit" after it, rules it out. "FY2019", "(2019)" and "in 2019." are still caught.
YEAR = re.compile(r"(?<!\d)(?<!\d\.)(?:19|20)\d{2}(?!\d)(?!\.\d)")
ACCESSION = re.compile(r"\b\d{10}-\d{2}-\d{6}\b")


@lru_cache(maxsize=1)
def _universe() -> tuple[tuple[str, ...], tuple[re.Pattern, ...]]:
    from ingest.universe import load_universe
    companies = load_universe()
    tickers = tuple(c["ticker"] for c in companies if len(c["ticker"]) >= 2)
    # Case-sensitive on purpose: "Target" the company is capitalised, "target" the word is not.
    # Names written in capitals (NVIDIA) are caught by the second alternative.
    names = tuple(re.compile(rf"(?<![A-Za-z])(?:{re.escape(c['name'])}|{re.escape(c['name'].upper())})(?![A-Za-z])")
                  for c in companies)
    return tickers, names


def find_leaks(text: str) -> list[str]:
    """Every problem found in `text`, as short human-readable strings. Empty means clean."""
    problems: list[str] = []
    for m in YEAR.finditer(text):
        problems.append(f"year {m.group(0)}")
    for m in ACCESSION.finditer(text):
        problems.append(f"accession number {m.group(0)}")
    tickers, names = _universe()
    for t in tickers:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", text):
            problems.append(f"ticker {t}")
    for pat in names:
        m = pat.search(text)
        if m:
            problems.append(f"company name {m.group(0)}")
    return problems
