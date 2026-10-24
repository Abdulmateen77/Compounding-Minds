"""Turn a raw SEC `submissions` JSON into event rows and the company's SIC code (README 4.1).

The SEC shape this reads (the newest ~1000 filings; older ones are in extra files):

    {"cik": "0000320193", "sic": "3571", "filings": {
        "recent": {"accessionNumber": [...], "filingDate": [...], "form": [...],
                   "items": ["2.02,9.01", ...], "primaryDocument": [...]},
        "files": [{"name": "CIK0000320193-submissions-001.json", ...}]}}

Each filing becomes one event row. 8-K `items` are the item codes, which is how we find an auditor
change (item 4.01). 10-K and 10-Q rows carry `text_ref` so a later pass can search the text for
going-concern language and fill `going_concern_hits`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

EVENT_FORMS = frozenset({"8-K", "8-K/A", "10-K", "10-K/A", "10-Q", "10-Q/A"})
AUDITOR_CHANGE_ITEM = "4.01"


@dataclass
class Submissions:
    sic: str | None
    events: list[dict] = field(default_factory=list)
    extra_files: list[str] = field(default_factory=list)  # older pages the fetcher must also download


def filing_url(cik: str | int, accession: str, document: str) -> str:
    """Where to download a filing document from."""
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{document}")


def parse_filings_block(block: dict, company_id: str) -> list[dict]:
    """`block` is filings.recent, or the top level of an older-pages file. Parallel arrays."""
    n = len(block.get("accessionNumber", []))
    items = block.get("items") or [""] * n
    docs = block.get("primaryDocument") or [""] * n
    rows = []
    for i in range(n):
        form = block["form"][i]
        if form not in EVENT_FORMS:
            continue
        accession = block["accessionNumber"][i]
        rows.append({
            "company_id": company_id,
            "form": form,
            "items": [x.strip() for x in items[i].split(",") if x.strip()] if form.startswith("8-K") else [],
            "filed_date": date.fromisoformat(block["filingDate"][i]),
            "accession": accession,
            "text_ref": f"{accession}/{docs[i]}" if docs[i] and not form.startswith("8-K") else None,
        })
    return rows


def parse_submissions(data: dict, company_id: str) -> Submissions:
    filings = data.get("filings", {})
    return Submissions(
        sic=str(data["sic"]) if data.get("sic") else None,
        events=parse_filings_block(filings.get("recent", {}), company_id),
        extra_files=[f["name"] for f in filings.get("files", [])],
    )
