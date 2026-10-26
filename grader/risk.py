"""Resolve the Risk agent's `distress_event_12m` call against filings made after `as_of`.

The call is "yes" if, in the 12 months after as_of, any of these happen:
  * auditor change: an 8-K with item 4.01                       -> pure Python
  * going-concern language in a 10-K / 10-Q                     -> keyword filter + Sapling
  * dividend cut of at least 25%                                -> pure Python on store facts

Why Sapling for going concern: "going concern" and "substantial doubt" appear in plenty of
healthy filings (risk factors, accounting policy notes, "no substantial doubt exists"), so a
keyword hit alone over-reports distress. Python finds the passages; Sapling judges them
against a written policy. Sapling saying there isn't enough information (or the text
contradicts itself) makes the call `unresolvable`, which README 6.2 excludes from accuracy.

Filings are read only through store.queries (the point-in-time gate), at the window end.
The caller must only grade once the window end is visible in the replay.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from ingest.events import strip_html
from ingest.sec import raw_root
from schemas import AgentCall, Event
from store import queries

from .config import (DIVIDEND_CUT_THRESHOLD, GOING_CONCERN_KEYWORDS, GOING_CONCERN_MAX_EVIDENCE_CHARS,
                     GOING_CONCERN_SNIPPET_CHARS, RISK_TEXT_FORMS, SAPLING_MIN_PROB_WHEN_UNSURE)
from .facts import Quarter, discrete_quarters, ttm
from .sapling import LABELS, SaplingClient, SaplingError, Verdict

QUESTION_ID = "distress_event_12m"
DEFAULT_FILINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "filings"


def filing_dirs() -> list[Path]:
    """Where `Event.text_ref` resolves: B's raw SEC cache first (ingest stores text_ref as
    `<cik>/<accession>/<doc>` under Archives/edgar/data), then the legacy data/filings/."""
    return [raw_root() / "sec" / "www.sec.gov" / "Archives" / "edgar" / "data", DEFAULT_FILINGS_DIR]

GOING_CONCERN_POLICY = (
    "A filing contains going-concern language only if management or the independent auditor "
    "concludes that substantial doubt currently exists about the reporting company's ability to "
    "continue as a going concern. These do not count: risk factors saying such doubt could arise "
    "in the future; statements that no substantial doubt exists; doubt that was raised but is "
    "stated to be alleviated by management's plans; descriptions of the going-concern basis of "
    "accounting; and doubt about a different entity such as a customer, supplier or investee."
)
GOING_CONCERN_CLAIM = (
    "This filing states that substantial doubt exists about the reporting company's ability "
    "to continue as a going concern."
)

TextLoader = Callable[[Event], "str | None"]
Check = Callable[[AgentCall, date], "tuple[str, dict]"]  # -> (yes|no|unresolvable, info)


def window_end(as_of: date) -> date:
    try:
        return as_of.replace(year=as_of.year + 1)
    except ValueError:  # 29 Feb
        return as_of.replace(year=as_of.year + 1, day=28)


def file_text_loader(filings_dir: Path | str | None = None) -> TextLoader:
    """Event.text_ref is a path to the filing, absolute or under one of `filing_dirs()` (or `filings_dir`).
    SEC documents are HTML, so tags are stripped: the keyword filter and Sapling see the words only."""
    bases = [Path(filings_dir)] if filings_dir else filing_dirs()

    def load(event: Event) -> str | None:
        if not event.text_ref:
            return None
        p = Path(event.text_ref)
        for f in [p] if p.is_absolute() else [b / p for b in bases]:
            if f.is_file():
                return strip_html(f.read_text(errors="ignore"))
        return None

    return load


def going_concern_excerpts(text: str) -> str:
    """Passages around each keyword hit, merged and capped. Empty string = no hits."""
    pat = re.compile("|".join(re.escape(k) for k in GOING_CONCERN_KEYWORDS), re.I)
    spans: list[list[int]] = []
    for m in pat.finditer(text):
        lo = max(0, m.start() - GOING_CONCERN_SNIPPET_CHARS)
        hi = min(len(text), m.end() + GOING_CONCERN_SNIPPET_CHARS)
        if spans and lo <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], hi)
        else:
            spans.append([lo, hi])
    parts = [" ".join(text[lo:hi].split()) for lo, hi in spans]
    out = "\n[...]\n".join(parts)
    return out[:GOING_CONCERN_MAX_EVIDENCE_CHARS]


def verdict_to_outcome(v: Verdict) -> str:
    """supported -> yes, violation -> no, not enough info / contradictory -> unresolvable.

    "unsure" means Sapling's calibrated set holds more than one label; we take its top label
    only when that label is confident enough (config), else unresolvable.
    """
    label = v.status if v.status in LABELS else None
    if label is None and v.probabilities.get(v.raw_label, 0.0) >= SAPLING_MIN_PROB_WHEN_UNSURE:
        label = v.raw_label
    return {"supported": "yes", "violation": "no"}.get(label, "unresolvable")


def check_auditor_change(events: list[Event]) -> tuple[str, dict]:
    hits = [e for e in events if e.form.startswith("8-K") and "4.01" in e.items]
    if hits:
        return "yes", {"accessions": [e.accession for e in hits], "filed": str(hits[0].filed_date)}
    return "no", {}


DIVIDEND_CONCEPTS = ("dividends_paid", "dividends_per_share")  # cash paid first, per-share as cross-check


def check_dividend_cut(company_id: str, as_of: date, end: date) -> tuple[str, dict]:
    """yes if TTM dividends fell >= DIVIDEND_CUT_THRESHOLD year over year at any quarter whose
    figures were filed in (as_of, end]. Visibility: facts are read at `end` through the store
    gate; a derived quarter counts from the later filing date of its inputs (Q4 = 10-K date).

    non-payer (no positive dividends before the window)   -> no
    payer but no comparable year-over-year pair in window -> unresolvable (data not filed yet,
        or the payer stopped and XBRL simply omits the fact: we do not guess either way)
    """
    pairs_seen = False
    for concept in DIVIDEND_CONCEPTS:
        qs = discrete_quarters(queries.get_facts(company_id, concept, end))
        if not qs:
            continue
        for q in qs:
            if not (as_of < q.visible <= end):
                continue
            now, then = ttm(qs, q.period_end), _year_before(qs, q)
            if now is None or then is None or then.value <= 0:
                continue
            pairs_seen = True
            if now.value <= (1 - DIVIDEND_CUT_THRESHOLD) * then.value:
                return "yes", {"concept": concept, "quarter": str(q.period_end), "ttm_now": now.value,
                               "ttm_year_before": then.value, "change": now.value / then.value - 1,
                               "accessions": sorted(set(now.accessions) | set(then.accessions)),
                               "filed": str(q.visible)}
        if pairs_seen:
            return "no", {"concept": concept}
    paid_before = any(q.value > 0 for c in DIVIDEND_CONCEPTS
                      for q in discrete_quarters(queries.get_facts(company_id, c, as_of)))
    if paid_before:
        return "unresolvable", {"reason": "dividend payer but no comparable year-over-year pair filed in the window"}
    return "no", {"reason": "no dividends paid before the window"}


def _year_before(qs: list[Quarter], q: Quarter) -> Quarter | None:
    prior = [x for x in qs if 350 <= (q.period_end - x.period_end).days <= 380]
    return ttm(qs, prior[0].period_end) if prior else None


def check_going_concern(events: list[Event], sapling: SaplingClient,
                        load_text: TextLoader) -> tuple[str, dict]:
    filings = [e for e in events if e.form in RISK_TEXT_FORMS]
    if not filings:
        return "unresolvable", {"reason": "no 10-K or 10-Q filed in the window"}
    per_filing, unresolved = [], False
    for e in filings:
        row: dict = {"accession": e.accession, "form": e.form, "filed": str(e.filed_date)}
        text = load_text(e)
        if text is None:
            row["result"], unresolved = "unresolvable", True
            row["reason"] = "filing text not available"
        elif not (excerpts := going_concern_excerpts(text)):
            row["result"] = "no"  # no keyword at all: no need to ask Sapling
        else:
            evidence = f"Excerpts from a {e.form} filed on {e.filed_date}:\n{excerpts}"
            try:
                v = sapling.verify(GOING_CONCERN_POLICY, evidence, GOING_CONCERN_CLAIM)
            except SaplingError as err:  # endpoint down, or replay_only with no saved verdict
                row["result"], row["reason"], unresolved = "unresolvable", f"Sapling unavailable: {err}", True
                per_filing.append(row)
                continue
            row["result"], row["sapling"] = verdict_to_outcome(v), v.as_dict()
            if row["result"] == "yes":
                per_filing.append(row)
                return "yes", {"filings": per_filing}
            unresolved |= row["result"] == "unresolvable"
        per_filing.append(row)
    return ("unresolvable" if unresolved else "no"), {"filings": per_filing}


_METRIC = {"auditor_change": "auditor_changes_5y", "going_concern": "going_concern_hits",
           "dividend_cut": "dividend_cut_history_5y"}


def resolve_distress(call: AgentCall, sapling: SaplingClient | None = None,
                     load_text: TextLoader | None = None,
                     extra_checks: dict[str, Check] | None = None) -> tuple[str, dict]:
    """OutcomeFn for the Risk agent: (call) -> (yes|no|unresolvable, info)."""
    if call.claim.question_id != QUESTION_ID:
        raise ValueError(f"resolve_distress only handles {QUESTION_ID}, got {call.claim.question_id}")
    end = window_end(call.as_of)
    events = [e for e in queries.get_events(call.company_id, end) if e.filed_date > call.as_of]
    events = [e for e in events if e.filed_date <= end]

    components: dict[str, tuple[str, dict]] = {"auditor_change": check_auditor_change(events)}
    if components["auditor_change"][0] != "yes":  # skip Sapling when the answer is already yes
        components["going_concern"] = check_going_concern(events, sapling or SaplingClient(),
                                                          load_text or file_text_loader())
    components["dividend_cut"] = check_dividend_cut(call.company_id, call.as_of, end)
    for name, fn in (extra_checks or {}).items():
        components[name] = fn(call, end)

    results = [r for r, _ in components.values()]
    outcome = "yes" if "yes" in results else "unresolvable" if "unresolvable" in results else "no"
    info = {"rule": QUESTION_ID, "resolution_date": str(end),
            "window": [str(call.as_of + timedelta(days=1)), str(end)],
            "components": {k: {"result": r, **d} for k, (r, d) in components.items()},
            "decisive_metrics": [_METRIC[k] for k, (r, _) in components.items() if r == "yes"]
            or list(_METRIC.values())}
    return outcome, info
