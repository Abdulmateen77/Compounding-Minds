"""LLMGateway + ModelUpdater: our code depends on these interfaces, not on Mubit's API (README 10).

OPEN (ask at Mubit office hours): exact update endpoint and payload, update latency,
per-agent isolation, rate limits, how version ids are exposed. Do NOT guess endpoints:
`MubitGateway`/`MubitUpdater` are deliberately unimplemented until confirmed.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from schemas import Correction


class LLMGateway(ABC):
    """All LLM calls go through here -> Mubit base URL."""

    @abstractmethod
    def complete(self, agent: str, messages: list[dict], **kw) -> str: ...


@dataclass(frozen=True)
class UpdateRef:
    agent: str
    ref: str
    fallback: bool = False


@dataclass(frozen=True)
class UpdateStatus:
    state: str  # pending | applied | failed
    model_version: str | None = None


class ModelUpdater(ABC):
    @abstractmethod
    def submit_corrections(self, agent: str, corrections: list[Correction]) -> UpdateRef: ...

    @abstractmethod
    def get_model_version(self, agent: str) -> str: ...

    @abstractmethod
    def status(self, ref: UpdateRef) -> UpdateStatus: ...


class MubitGateway(LLMGateway):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or os.environ.get("MUBIT_BASE_URL", "")
        self.api_key = api_key or os.environ.get("MUBIT_API_KEY", "")

    def complete(self, agent, messages, **kw):
        raise NotImplementedError("Confirm Mubit's LLM endpoint at office hours, then implement here.")


class MubitUpdater(ModelUpdater):
    def submit_corrections(self, agent, corrections):
        raise NotImplementedError("Confirm Mubit's update API at office hours.")

    def get_model_version(self, agent):
        raise NotImplementedError

    def status(self, ref):
        raise NotImplementedError


class FakeModelUpdater(ModelUpdater):
    """FALLBACK ONLY. Appends lessons to a per-agent memory file; label it in the UI if used.

    The memory text is what `agents.runner` injects into the prompt, so the demo loop
    still shows lesson -> new version -> changed behaviour.
    """

    def __init__(self, memory_dir: Path | str = "agents/memory"):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _mem(self, agent: str) -> Path:
        return self.dir / f"{agent}.jsonl"

    def lessons(self, agent: str) -> list[str]:
        p = self._mem(agent)
        return [json.loads(l)["lesson"] for l in p.read_text().splitlines()] if p.exists() else []

    def submit_corrections(self, agent, corrections):
        with self._mem(agent).open("a") as f:
            for c in corrections:
                f.write(json.dumps({"correction_id": c.correction_id, "lesson": c.lesson}) + "\n")
        return UpdateRef(agent, f"fake:{agent}:{len(self.lessons(agent))}", fallback=True)

    def get_model_version(self, agent):
        return f"fallback/{agent}-v{len(self.lessons(agent))}"

    def status(self, ref):
        return UpdateStatus("applied", self.get_model_version(ref.agent))


class ScriptedGateway(LLMGateway):
    """Offline gateway for tests and stub-mode dev: a function maps (agent, messages) -> text."""

    def __init__(self, fn: Callable[[str, list[dict]], str]):
        self.fn = fn

    def complete(self, agent, messages, **kw):
        return self.fn(agent, messages)
