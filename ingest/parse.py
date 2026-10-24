"""companyfacts JSON -> `facts` rows (store/schema.sql). Pure function, no I/O.

* every row carries `filed_date` (the SEC `filed` field), `accession` and `form`
* a restatement is a NEW row (different accession/filed_date); nothing is overwritten
* a later filing that merely repeats an already-known value for the same (concept, period) is
  dropped: it adds no information at any as-of date, and the earliest filing keeps the credit
* fallback tags only fill periods the earlier tags do not cover (A's resolve_concept rule)
* row keys == store/schema.sql `facts` columns minus the DB-generated id/period_start_key
"""
from __future__ import annotations

from datetime import date

from .concepts import CONCEPT_MAP, Concept

PERIODIC_FORMS = ("10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-KT/A", "20-F", "40-F", "20-F/A", "40-F/A")


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def parse_companyfacts(company_id: str, data: dict, concept_map: dict[str, Concept] | None = None,
                       forms: tuple[str, ...] = PERIODIC_FORMS) -> list[dict]:
    cmap = CONCEPT_MAP if concept_map is None else concept_map
    ns = data.get("facts", {}).get("us-gaap", {})
    out: list[dict] = []
    for concept, spec in cmap.items():
        by_tag = {tag: _tag_rows(company_id, concept, tag, spec.unit, ns.get(tag, {}).get("units", {}).get(spec.unit, []),
                                 forms) for tag in spec.tags}
        out += _resolve(by_tag, spec.tags)
    out.sort(key=lambda r: (r["concept"], r["filed_date"], r["period_end"]))
    return out


def _resolve(by_tag: dict[str, list[dict]], tags: tuple[str, ...]) -> list[dict]:
    """Same rule as store.concepts.resolve_concept: per (period_start, period_end) the best-ranked
    tag that has the period wins; all of that tag's rows (restatements) are kept."""
    rank = {t: i for i, t in enumerate(tags)}
    best: dict[tuple, str] = {}
    for tag, rows in by_tag.items():
        for r in rows:
            k = (r["period_start"], r["period_end"])
            if k not in best or rank[tag] < rank[best[k]]:
                best[k] = tag
    return [r for tag, rows in by_tag.items() for r in rows if best[(r["period_start"], r["period_end"])] == tag]


def _tag_rows(company_id, concept, tag, unit, entries, forms) -> list[dict]:
    rows = []
    for e in entries:
        if e.get("form") not in forms or not e.get("filed") or not e.get("end") or e.get("val") is None:
            continue
        rows.append({
            "company_id": company_id, "concept": concept, "source_tag": tag, "value": float(e["val"]), "unit": unit,
            "period_start": _d(e.get("start")), "period_end": _d(e["end"]),
            "fiscal_year": e.get("fy"), "fiscal_period": e.get("fp"), "form": e["form"], "accession": e["accn"],
            "filed_date": _d(e["filed"]),
        })
    rows.sort(key=lambda r: (r["filed_date"], r["accession"]))
    seen: dict[tuple, float] = {}  # latest known value per (period_start, period_end)
    kept = []
    for r in rows:
        k = (r["period_start"], r["period_end"])
        if k in seen and seen[k] == r["value"]:
            continue  # same value re-reported later: no new information
        seen[k] = r["value"]
        kept.append(r)
    return kept
