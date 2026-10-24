"""Metrics engine (Person A). Python computes every number an agent sees; no LLM is involved.
Entry point: `get_metrics(company_id, agent, as_of)`. Formulas: metrics/SPEC.md."""
from .engine import AGENT_METRICS, MAX_MISSING, get_metrics

__all__ = ["get_metrics", "AGENT_METRICS", "MAX_MISSING"]
