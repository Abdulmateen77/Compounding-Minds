"""Turn a raw SEC `companyfacts` JSON into fact rows (README 4.1, store/concepts.py).

Pure functions, no network and no database, so Person B's fetcher only has to save the JSON
and call `parse_companyfacts`. The SEC shape this reads:

    {"cik": 320193, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"start": "2018-01-01", "end": "2018-03-31", "val": 100, "accn": "0000320193-18-000070",
         "fy": 2018, "fp": "Q2", "form": "10-Q", "filed": "2018-05-02"}, ...]}}}}}

Rules:
  * only 10-K and 10-Q (and their /A amendments) become facts: they are the filings our
    questions are graded on
  * only the unit our concept expects (USD, or USD/shares), so a tag reported in two currencies
    cannot mix
  * balance-sheet facts have no `start`. A duration fact with no `start` is dropped
  * the SAME value repeated in a later filing (a prior-year comparative) is kept as its own row:
    it has its own accession and filed_date, and the gate picks the latest visible one
  * `fy` and `fp` describe the FILING, not the period. They are kept for reference only
"""
from __future__ import annotations

from datetime import date

from store.concepts import ALL_TAGS, CONCEPTS, TAG_TO_CONCEPT, resolve_concept

FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def parse_companyfacts(data: dict, company_id: str, taxonomy: str = "us-gaap") -> list[dict]:
    by_concept: dict[str, dict[str, list[dict]]] = {}
    for tag, body in data.get("facts", {}).get(taxonomy, {}).items():
        if tag not in ALL_TAGS:
            continue
        concept = CONCEPTS[TAG_TO_CONCEPT[tag]]
        for unit, entries in body.get("units", {}).items():
            if unit != concept.unit:
                continue
            for e in entries:
                if e.get("form") not in FORMS or e.get("val") is None:
                    continue
                start = _d(e.get("start")) if concept.kind == "duration" else None
                if concept.kind == "duration" and start is None:
                    continue
                by_concept.setdefault(concept.key, {}).setdefault(tag, []).append({
                    "company_id": company_id,
                    "value": float(e["val"]),
                    "unit": unit,
                    "period_start": start,
                    "period_end": _d(e["end"]),
                    "fiscal_year": e.get("fy"),
                    "fiscal_period": e.get("fp"),
                    "form": e["form"],
                    "accession": e["accn"],
                    "filed_date": _d(e["filed"]),
                })
    out: list[dict] = []
    seen: set[tuple] = set()
    for key, rows_by_tag in by_concept.items():
        for r in resolve_concept(key, rows_by_tag):
            ident = (r["concept"], r["unit"], r["period_start"], r["period_end"], r["accession"])
            if ident not in seen:
                seen.add(ident)
                out.append(r)
    out.sort(key=lambda r: (r["concept"], r["period_end"], r["filed_date"], r["period_start"] or date.min))
    return out
