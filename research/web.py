"""What has happened lately: recent news about a company, found with Firecrawl and summarised with a guard.

Words and links only. No figure on the page ever comes from here: every number is computed from SEC filings. A
summary line must point at one article and may only use numbers that appear in that article's own text; anything
else is dropped. News is fetched for today's report only. It is not dated to what was known at a past date, so it
never feeds the replay or the back-test.

Firecrawl is called through its command-line tool, which uses either FIRECRAWL_API_KEY from the environment or the
credentials stored by `firecrawl login`. If neither works, or the network is down, the report simply has no news
section. Each search costs two credits, so results are cached on disk for twelve hours.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

CACHE_DIR = Path(os.environ.get("RAW_CACHE_DIR", "data/raw")) / "web"
CACHE_TTL_S = 12 * 3600
MAX_ITEMS = 6
MAX_AGE_DAYS = 45
SNIPPET_CHARS = 700
_AGE = re.compile(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", re.I)
_UNIT_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30}


def _firecrawl() -> str | None:
    return shutil.which("firecrawl")


def run_cli(args: list[str], timeout: int = 60) -> dict | None:
    """Run the Firecrawl command line and return its JSON, or None on any failure."""
    exe = _firecrawl()
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, encoding="utf-8")
        start = out.stdout.find("{")
        data = json.loads(out.stdout[start:]) if start != -1 else None
        return data if isinstance(data, dict) and data.get("success") else None
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


def age_days(text: str | None) -> int | None:
    """"3 days ago" -> 3; "2 hours ago" -> 0; anything else -> None."""
    m = _AGE.search(text or "")
    return None if not m else int(m.group(1)) * _UNIT_DAYS[m.group(2).lower()]


def clean(snippet: str) -> str:
    """Article text from a search snippet: no markdown links, images, headings or whitespace noise."""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", snippet or "")
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[#*_>`]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def short_name(name: str) -> str:
    """"Tesla, Inc." -> "Tesla"; "Coca Cola Co" -> "Coca Cola"."""
    first = re.sub(r"\b(inc|corp|corporation|co|company|ltd|plc|holdings?|group|the|class [a-c])\b\.?", " ", name, flags=re.I)
    return re.sub(r"[^A-Za-z0-9 &'-]", " ", first).strip()


def relevant(item: dict, name: str, ticker: str | None) -> bool:
    """The company is named in the headline (a snippet alone can be about something else)."""
    title = (item.get("title") or "").lower()
    n = short_name(name).lower()
    return bool(n and n in title) or bool(ticker and re.search(rf"\b{re.escape(ticker.lower())}\b", title))


def fetch(name: str, ticker: str | None, today: date | None = None, runner=run_cli, cache_dir: Path | None = None) -> dict | None:
    """Recent news items for a company: [{title, url, source, age, age_days, text}] newest first, or None."""
    today = today or date.today()
    cache = (cache_dir or CACHE_DIR) / f"{(ticker or short_name(name)).lower().replace(' ', '_')}_{today.isoformat()}.json"
    try:
        if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL_S:
            return json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    query = re.sub(r"[^A-Za-z0-9 ]", " ", f"{short_name(name)} {ticker or ''} stock news").strip()
    data = runner(["search", query, "--sources", "news", "--tbs", "qdr:m", "--limit", "10", "--json"])
    if not data:
        return None
    raw = (data.get("data") or {}).get("news") or []
    items, seen = [], set()
    for r in raw:
        url, title = r.get("url") or "", (r.get("title") or "").strip()
        if not url or not title or not relevant(r, name, ticker):
            continue
        days = age_days(r.get("date"))
        if days is not None and days > MAX_AGE_DAYS:
            continue
        key = re.sub(r"\W+", "", title.lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        items.append({"title": title, "url": url, "source": urlparse(url).netloc.removeprefix("www."),
                      "age": r.get("date"), "age_days": days, "text": clean(r.get("snippet"))[:SNIPPET_CHARS]})
    items.sort(key=lambda i: (i["age_days"] is None, i["age_days"] or 0))
    out = {"retrieved": today.isoformat(), "items": items[:MAX_ITEMS], "credits_used": data.get("creditsUsed")}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        pass
    return out


# ---- the summary, with a guard on every number ---------------------------------------------------------------------
SYSTEM = (
    "You summarise recent news about one company for an ordinary reader. You are given numbered articles (headline and "
    "the opening text). Write up to five short, plain, neutral sentences, each about ONE article and naming its source "
    "(for example: Reuters reports that ...). Cover what actually changed or was announced. Use only what an article "
    "says: do not add facts, numbers, forecasts or background from anywhere else, and do not predict the share price or "
    "tell the reader to buy, sell or hold. Every number you write must appear in that article's text. If the articles say "
    "nothing useful, return an empty list. Reply with JSON only: {\"items\": [{\"n\": <article number>, \"text\": \"...\"}]}."
)
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")

def numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "").rstrip(".") for m in NUM.finditer(text)}


def summarise(gateway, company: str, news: dict | None) -> list[dict]:
    """Up to five summary lines, each tied to one article and checked against that article's own numbers."""
    if not news or not news.get("items"):
        return []
    items = news["items"]
    body = "\n\n".join(f"[{i + 1}] {it['source']} ({it['age'] or 'recent'}): {it['title']}\n{it['text']}" for i, it in enumerate(items))
    try:
        raw = gateway.complete("research_news", [{"role": "system", "content": SYSTEM},
                                                 {"role": "user", "content": f"Company: {company}\n\n{body}"}],
                               purpose="research_news", max_tokens=700, session_id=f"news:{company}")
        got = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))["items"]
    except Exception:
        return []
    out = []
    for g in got[:5]:
        try:
            n, text = int(g["n"]), str(g["text"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not 1 <= n <= len(items) or not text:
            continue
        src = items[n - 1]
        if numbers(text) - numbers(src["title"] + " " + src["text"]):      # strict: even 3% must be in the article
            continue                                              # a number the article does not contain
        out.append({"text": text, "url": src["url"], "source": src["source"], "title": src["title"], "age": src["age"]})
    return out


def build(gateway, name: str, ticker: str | None, today: date | None = None, runner=run_cli, cache_dir: Path | None = None) -> dict | None:
    news = fetch(name, ticker, today, runner, cache_dir)
    if news is None:
        return None
    lines = summarise(gateway, name, news) if gateway is not None else []
    return {"retrieved": news["retrieved"], "lines": lines, "articles": news["items"]}
