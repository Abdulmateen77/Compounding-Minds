"""Per-agent adapters. `get_adapter("risk")` returns that agent's adapter."""
from .base import AgentAdapter
from .fundamentals import ADAPTER as FUNDAMENTALS
from .risk import ADAPTER as RISK
from .scenarios import ADAPTER as SCENARIOS

ADAPTERS: dict[str, AgentAdapter] = {a.agent: a for a in (FUNDAMENTALS, RISK, SCENARIOS)}


def get_adapter(agent: str) -> AgentAdapter:
    try:
        return ADAPTERS[agent]
    except KeyError:
        raise KeyError(f"no adapter for agent {agent!r}; have {sorted(ADAPTERS)}") from None
