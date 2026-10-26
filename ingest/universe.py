"""Load and validate the company universe (README 4.2). Person A owns the list; Person B's
ingest reads it, resolves each ticker to a CIK and loads the `companies` table."""
from __future__ import annotations

import json
import re
from pathlib import Path

PATH = Path(__file__).parent / "universe.json"
SIZE = 50
HELD_OUT = 10
_ID = re.compile(r"^anon_\d{3}$")
COVID_GROUPS = ("hit", "resilient", "mixed")
# Not supported by the metric set: their statements do not have FCF, gross margin or
# debt/EBITDA in the usual sense.
UNSUPPORTED_SECTORS = ("Financials", "Real Estate")


def load_universe(path: Path = PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    companies = data["companies"]
    validate(companies)
    return companies


def validate(companies: list[dict]) -> None:
    """Raises ValueError with every problem found, so a bad edit is fixed in one pass."""
    problems: list[str] = []
    if len(companies) != SIZE:
        problems.append(f"expected {SIZE} companies, found {len(companies)}")
    for key in ("company_id", "ticker", "name"):
        vals = [c[key] for c in companies]
        if len(set(vals)) != len(vals):
            problems.append(f"duplicate {key}")
    for c in companies:
        if not isinstance(c.get("short_history", False), bool):
            problems.append(f"{c['company_id']}: short_history must be true or false")
        if not _ID.match(c["company_id"]):
            problems.append(f"bad company_id {c['company_id']!r}")
        if c["covid_group"] not in COVID_GROUPS:
            problems.append(f"{c['company_id']}: bad covid_group {c['covid_group']!r}")
        if c["sector"] in UNSUPPORTED_SECTORS:
            problems.append(f"{c['company_id']}: sector {c['sector']} is not supported by the metrics")
    held = [c for c in companies if c["held_out"]]
    if len(held) != HELD_OUT:
        problems.append(f"expected {HELD_OUT} held-out companies, found {len(held)}")
    for group in COVID_GROUPS:
        n = sum(1 for c in companies if c["covid_group"] == group)
        if n < 8:
            problems.append(f"covid_group {group!r} has only {n} companies (need at least 8)")
    if len({c["sector"] for c in held}) < 5:
        problems.append("held-out companies should cover at least 5 sectors")
    if problems:
        raise ValueError("; ".join(problems))


def held_out_ids(companies: list[dict] | None = None) -> set[str]:
    return {c["company_id"] for c in (companies or load_universe()) if c["held_out"]}


def train_ids(companies: list[dict] | None = None) -> set[str]:
    return {c["company_id"] for c in (companies or load_universe()) if not c["held_out"]}
