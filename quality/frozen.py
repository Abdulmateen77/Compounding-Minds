"""The frozen twin: the same agent, with the same prompts, that is never updated (BRIEF_HERMES H2).

It is the control for the learning claim. If the learned agent does not beat its frozen twin,
the learning loop has not shown it works, and the held-out report says so.
"""
from __future__ import annotations

import os
from datetime import date

from agents.gateway import DEFAULT_MODEL, LLMGateway, ModelUpdater, UpdateRef, UpdateStatus
from agents.runner import run_agent
from schemas import AgentCall, Correction


class FrozenUpdater(ModelUpdater):
    """Ignores every correction. Its model version never changes."""

    def __init__(self, base: str | None = None):
        self.base = base or os.environ.get("MUBIT_MODEL") or DEFAULT_MODEL

    def get_model_version(self, agent: str) -> str:
        return f"{self.base}-frozen"

    def submit_corrections(self, agent: str, corrections: list[Correction]) -> UpdateRef:
        return UpdateRef(agent, "frozen")

    def status(self, ref: UpdateRef) -> UpdateStatus:
        return UpdateStatus("applied", self.get_model_version(ref.agent))

    def lessons(self, agent: str) -> list[str]:
        return []


def run_frozen(agent: str, company_id: str, as_of: date, metrics: dict, gateway: LLMGateway,
               run_id: str | None = None, updater: FrozenUpdater | None = None) -> AgentCall | None:
    """One call by the frozen twin. `lessons=[]` is passed explicitly, so even a caller that
    hands in a lesson-bearing updater cannot leak lessons into the control."""
    return run_agent(agent, company_id, as_of, metrics, gateway, updater or FrozenUpdater(),
                     run_id=run_id, lessons=[])
