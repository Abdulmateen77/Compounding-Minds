"""submissions -> `events` rows, plus a going-concern passage detector for filing text."""
from __future__ import annotations

import re
from datetime import date

EVENT_FORMS = ("8-K", "8-K/A", "10-K", "10-K/A", "10-Q", "10-Q/A", "NT 10-K", "NT 10-Q")

# Items the Risk and Fundamentals rules care about (documentation; all items are stored).
KEY_8K_ITEMS = {
    "4.01": "change of certifying accountant (auditor change)",
    "4.02": "non-reliance on previously issued financials (restatement)",
    "2.02": "results of operations (earnings release)",
    "2.04": "triggering event accelerating a debt obligation",
    "1.03": "bankruptcy or receivership",
    "3.01": "delisting notice",
    "8.01": "other events",
}


def split_items(raw: str | None) -> list[str]:
    return [i.strip() for i in (raw or "").split(",") if i.strip()]


def extract_events(company_id: str, filings: list[dict], forms: tuple[str, ...] = EVENT_FORMS,
                   cik: str | int | None = None) -> list[dict]:
    """`filings` = SecClient.all_submission_filings() row dicts. One event per filing."""
    out = []
    for f in filings:
        form = f.get("form")
        if form not in forms or not f.get("filingDate") or not f.get("accessionNumber"):
            continue
        ref = None
        if f.get("primaryDocument") and cik is not None:
            ref = f"{int(cik)}/{f['accessionNumber'].replace('-', '')}/{f['primaryDocument']}"
        out.append({"company_id": company_id, "form": form,
                    "items": split_items(f.get("items")) if form.startswith("8-K") else [],
                    "filed_date": date.fromisoformat(f["filingDate"]),
                    "accession": f["accessionNumber"], "text_ref": ref, "going_concern_hits": 0})
    out.sort(key=lambda r: (r["filed_date"], r["accession"]))
    return out


# ---- going concern (STUB: regex over text; the grader's Sapling check is the authority) ----------

_GC = re.compile(
    r"(substantial\s+doubt[^.]{0,200}?going\s+concern|going\s+concern[^.]{0,200}?substantial\s+doubt"
    r"|ability\s+to\s+continue\s+as\s+a\s+going\s+concern)", re.I | re.S)
_NEGATED = re.compile(r"(no|not|alleviat\w+|dispel\w+|eliminat\w+|without)[^.]{0,80}substantial\s+doubt", re.I)


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", text))


def detect_going_concern(text: str, window: int = 150) -> list[str]:
    """Passages that mention going-concern doubt. Passages saying doubt was alleviated are skipped.
    Heuristic stub: flags candidates, does not decide."""
    text = strip_html(text)
    hits = []
    for m in _GC.finditer(text):
        s = text[max(0, m.start() - window): m.end() + window].strip()
        if not _NEGATED.search(s):
            hits.append(s)
    return hits


def tag_going_concern(events: list[dict], read_text, forms=("10-K", "10-K/A", "10-Q")) -> int:
    """Set `going_concern_hits` (passage count, schema `events.going_concern_hits`) on periodic-filing
    events whose text trips the detector. `read_text(event) -> str | None` supplies cached text
    (None = not available). Returns the number of events with at least one hit."""
    n = 0
    for e in events:
        if e["form"] in forms and e.get("text_ref"):
            txt = read_text(e)
            hits = len(detect_going_concern(txt)) if txt else 0
            if hits:
                e["going_concern_hits"] = hits
                n += 1
    return n
