"""Per-agent adapters. `get_adapter("risk")` returns that agent's adapter."""
from .base import AgentAdapter
from .fundamentals import ADAPTER as FUNDAMENTALS
from .moat import ADAPTER as MOAT
from .risk import ADAPTER as RISK
from .scenarios import ADAPTER as SCENARIOS
from .valuation import ADAPTER as VALUATION

ADAPTERS: dict[str, AgentAdapter] = {a.agent: a for a in (FUNDAMENTALS, RISK, SCENARIOS, VALUATION, MOAT)}


def get_adapter(agent: str) -> AgentAdapter:
    try:
        return ADAPTERS[agent]
    except KeyError:
        raise KeyError(f"no adapter for agent {agent!r}; have {sorted(ADAPTERS)}") from None
