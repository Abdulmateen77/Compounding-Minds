"""One adapter per agent (TASKS B2). Each owns its identity in Mubit.

Mubit groups calls into a task by system prompt + model (see MubitGateway), so an agent's
identity IS its stable system prompt. The adapter exposes that prompt and the task name so
the console, the batch sender and the eval harness all agree on which agent is which.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from schemas import AgentCall

from ..gateway import LLMGateway, ModelUpdater
from ..runner import build_messages, run_agent
from ..specs import SPECS, AgentSpec


@dataclass(frozen=True)
class AgentAdapter:
    agent: str

    @property
    def spec(self) -> AgentSpec:
        return SPECS[self.agent]

    @property
    def identity(self) -> str:
        """Stable name for this agent's Mubit task."""
        return f"cm-{self.agent}-{self.spec.investor}"

    def system_prompt(self) -> str:
        """The system prompt Mubit keys the task on. Identical for every call of this agent."""
        placeholder = {"metrics": []}
        return build_messages(self.agent, "anon_000", date(2000, 1, 1), placeholder, [])[0]["content"]

    def run(self, company_id: str, as_of: date, metrics: dict, gateway: LLMGateway,
            updater: ModelUpdater, run_id: str | None = None, lessons: list[str] | None = None) -> AgentCall | None:
        return run_agent(self.agent, company_id, as_of, metrics, gateway, updater, run_id=run_id, lessons=lessons)
