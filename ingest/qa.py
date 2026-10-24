"""Ingest QA report: coverage and gaps per company. Pure over a Dataset."""
from __future__ import annotations

from .concepts import CONCEPT_MAP
from .load import Dataset


def qa_report(ds: Dataset, concept_map=None, min_periods: int = 8) -> dict:
    cmap = CONCEPT_MAP if concept_map is None else concept_map
    per: dict[str, dict] = {}
    for c in ds.companies:
        cid = c["company_id"]
        facts = [f for f in ds.facts if f["company_id"] == cid]
        events = [e for e in ds.events if e["company_id"] == cid]
        by_concept: dict[str, set] = {}
        for f in facts:
            by_concept.setdefault(f["concept"], set()).add(f["period_end"])
        missing = [k for k in cmap if k not in by_concept]
        thin = [k for k, v in by_concept.items() if len(v) < min_periods]
        dates = [f["filed_date"] for f in facts]
        per[cid] = {
            "ticker": c["ticker"], "facts": len(facts), "events": len(events),
            "eight_k": sum(e["form"].startswith("8-K") for e in events),
            "first_filed": min(dates).isoformat() if dates else None,
            "last_filed": max(dates).isoformat() if dates else None,
            "concepts_covered": len(by_concept), "concepts_total": len(cmap),
            "missing_concepts": missing, "thin_concepts": sorted(thin),
            "restated_periods": _restated(facts), "problems": ds.gaps.get(cid, []),
            "ok": bool(facts) and bool(events) and not ds.gaps.get(cid) and len(missing) <= len(cmap) // 3,
        }
    return {"companies": per, "macro_series": sorted({r["series_id"] for r in ds.macro}),
            "macro_problems": ds.gaps.get("macro", []), "price_rows": len(ds.prices),
            "totals": {"companies": len(ds.companies), "facts": len(ds.facts), "events": len(ds.events),
                       "macro": len(ds.macro), "ok": sum(p["ok"] for p in per.values())}}


def _restated(facts: list[dict]) -> int:
    seen: dict[tuple, int] = {}
    for f in facts:
        k = (f["concept"], f["period_start"], f["period_end"])
        seen[k] = seen.get(k, 0) + 1
    return sum(v > 1 for v in seen.values())


def format_report(r: dict) -> str:
    t = r["totals"]
    lines = [f"Ingest QA: {t['ok']}/{t['companies']} companies OK, {t['facts']} facts, "
             f"{t['events']} events, {t['macro']} macro rows, {r['price_rows']} price rows", ""]
    for cid, p in r["companies"].items():
        lines.append(f"{cid} {p['ticker']:<6} {'OK ' if p['ok'] else 'GAP'} facts={p['facts']} events={p['events']} "
                     f"8-K={p['eight_k']} concepts={p['concepts_covered']}/{p['concepts_total']} "
                     f"filed={p['first_filed']}..{p['last_filed']} restated_periods={p['restated_periods']}")
        if p["missing_concepts"]:
            lines.append(f"    missing: {', '.join(p['missing_concepts'])}")
        if p["thin_concepts"]:
            lines.append(f"    thin (<8 periods): {', '.join(p['thin_concepts'])}")
        for pr in p["problems"]:
            lines.append(f"    problem: {pr}")
    if r["macro_series"] or r["macro_problems"]:
        lines.append(f"macro series: {', '.join(r['macro_series']) or 'none'}")
        lines += [f"    problem: {m}" for m in r["macro_problems"]]
    return "\n".join(lines)
