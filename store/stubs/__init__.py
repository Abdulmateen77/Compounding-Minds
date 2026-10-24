"""Stub metric bundles so Person B is never blocked on the real store (README 12).

`get_metrics_stub` has the same shape as the real `get_metrics`:
    {"company_id", "agent", "as_of", "metrics": [{name, value, unit, as_of, inputs}]}
Values are hand-made and NOT real company data.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

_DIR = Path(__file__).parent


def _load(agent: str) -> list[dict]:
    path = _DIR / f"metrics_{agent}.json"
    if not path.exists():
        raise KeyError(f"no stub metrics for agent {agent!r}")
    return json.loads(path.read_text())["bundles"]


def list_stub_cases(agent: str) -> list[tuple[str, date]]:
    return [(b["company_id"], date.fromisoformat(b["as_of"])) for b in _load(agent)]


def get_metrics_stub(company_id: str, agent: str, as_of: date) -> dict:
    """Exact (company, as_of) match if present, else the company's bundle re-stamped to as_of."""
    bundles = [b for b in _load(agent) if b["company_id"] == company_id] or _load(agent)
    exact = [b for b in bundles if b["as_of"] == as_of.isoformat()]
    b = (exact or bundles)[0]
    metrics = [{**m, "as_of": as_of.isoformat()} for m in b["metrics"]]
    return {"company_id": company_id, "agent": agent, "as_of": as_of.isoformat(), "metrics": metrics}
