"""Frozen twin: the same agent with learning switched off (README 8.4, 9).

Every learning agent is compared with its twin. The twin runs the same prompts, the same
model and the same principles, but never carries lessons and ignores corrections, so any
accuracy gap on held-out data comes from the corrections and nothing else.
"""
from __future__ import annotations

from schemas import Correction

from .gateway import DEFAULT_MODEL, ModelUpdater, UpdateRef, UpdateStatus


class FrozenUpdater(ModelUpdater):
    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODEL

    def lessons(self, agent: str) -> list[str]:
        return []

    def submit_corrections(self, agent: str, corrections: list[Correction]) -> UpdateRef:
        return UpdateRef(agent, f"frozen:{agent}:ignored", fallback=False)

    def get_model_version(self, agent: str) -> str:
        return f"frozen:{self.model}+{agent}-v0"

    def status(self, ref: UpdateRef) -> UpdateStatus:
        return UpdateStatus("applied", self.get_model_version(ref.agent))
