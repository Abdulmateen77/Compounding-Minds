"""LLMGateway + ModelUpdater: our code depends on these interfaces, not on Mubit's API (README 10).

MubitGateway follows docs.mubit.ai (Anthropic-compatible proxy). MubitUpdater documents a
gap: Mubit has no public corrections/outcomes endpoint, so lessons are applied in-prompt and
linked to Mubit request ids. Ask Mubit whether an outcome or rating API exists.
Findings from the docs and the questions still open: agents/MUBIT.md.
"""
from __future__ import annotations

import hashlib
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
    def complete(self, agent: str, messages: list[dict], record: bool = True, **kw) -> str: ...


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


DEFAULT_BASE_URL = "https://api.mubit.ai"
DEFAULT_MODEL = "claude-haiku-4-5"  # served by the Mubit starter credit; set MUBIT_MODEL to change


@dataclass(frozen=True)
class MubitRequest:
    """One call that went through Mubit. `request_id` (mreq_...) finds it in Mubit's console."""

    agent: str
    purpose: str
    request_id: str | None
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    system_sha: str | None = None   # first 12 hex of sha256(system prompt): with `model`, Mubit's task key
    recorded: bool = True           # False when sent with x-middleware-record: off


def system_sha(system: str) -> str:
    return hashlib.sha256(system.encode("utf-8")).hexdigest()[:12]


class ReplyTruncated(ValueError):
    """The model hit its output cap, so the reply is cut off mid-JSON. A ValueError so the runner treats it as an
    invalid reply (one repair retry, then a logged drop), and so the reply cache never stores it."""


# Why 4096 and not 1024: haiku-5-5 reasons before it answers, and that hidden reasoning counts toward
# max_tokens. At 1024, 9 of 14 Scenarios replies were cut off mid-JSON, and with the learned arm's lessons in
# the prompt (about 2,900 input tokens instead of 1,100) all 21 of 21 were. A normal reply needs 800 to 1,350.
DEFAULT_MAX_TOKENS = 4096
MAX_OUTPUT_TOKENS = 16000


class MubitGateway(LLMGateway):
    """Every LLM call goes through Mubit's Anthropic-compatible proxy.

    Per docs.mubit.ai ("Connect with the Anthropic SDK", "API reference"): base URL
    {host}/anthropic, the Mubit key in place of the provider key, model ids unchanged.
    Mubit records each call and returns its id in the `x-middleware-request-id` header.
    Mubit groups calls into tasks by system prompt + model, so each agent (and the
    reflection and synthesizer prompts) is its own task as long as its system prompt is stable.
    `complete(..., record=False)` sends `x-middleware-record: off`: the call is answered but Mubit keeps
    nothing, so it can't become a training example or use the task's daily review budget. Use it for
    held-out eval, probes and tests; never on calls Mubit should train on.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS, client=None, ledger=None):
        host = (base_url or os.environ.get("MUBIT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("MUBIT_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens
        if client is None:
            key = api_key or os.environ.get("MUBIT_API_KEY")
            if not key:
                raise RuntimeError("MUBIT_API_KEY is not set; put it in .env (gitignored)")
            from anthropic import Anthropic
            # max_retries 4: the SDK honours retry-after on 429/503/529. Tests inject `client` and never write a ledger.
            client = Anthropic(base_url=f"{host}/anthropic", api_key=key, max_retries=4, timeout=120)
            if ledger is None:
                from .ledger import CallLedger
                ledger = CallLedger()
        self.client = client
        self.ledger = ledger
        self.requests: list[MubitRequest] = []

    @property
    def last_request_id(self) -> str | None:
        return self.requests[-1].request_id if self.requests else None

    def complete(self, agent, messages, record: bool = True, **kw):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        sha = system_sha(system)
        convo = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        cap = kw.get("max_tokens", self.max_tokens)
        while True:
            params = {"model": self.model, "max_tokens": cap, "system": system, "messages": convo}
            if kw.get("session_id"):
                # On Anthropic, metadata.user_id is the one field Mubit reads as the session.
                params["metadata"] = {"user_id": str(kw["session_id"])[:200]}
            if not record:
                params["extra_headers"] = {"x-middleware-record": "off"}
            raw = self.client.messages.with_raw_response.create(**params)
            msg = raw.parse()
            usage = getattr(msg, "usage", None)
            req = MubitRequest(agent, kw.get("purpose", "call"), raw.headers.get("x-middleware-request-id"),
                               self.model, getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None),
                               system_sha=sha, recorded=record)
            self.requests.append(req)
            if self.ledger is not None:
                self.ledger.add(req)
            if getattr(msg, "stop_reason", None) != "max_tokens":
                break
            if cap >= MAX_OUTPUT_TOKENS:
                raise ReplyTruncated(f"{agent}: reply still cut off at max_tokens={cap}")
            cap = min(cap * 4, MAX_OUTPUT_TOKENS)     # rare at 4096; costs one more call, not a dropped one
        return "".join(getattr(b, "text", "") for b in msg.content)


# How many lessons go into one prompt. The file keeps every lesson (and the model version counts them all);
# the prompt gets the most recent ones, so it stays about 3,400 tokens instead of growing to ~17,000 by 2022.
MAX_LESSONS_IN_PROMPT = 40


class LessonMemory:
    """Per-agent lesson file. The runner puts the most recent lessons into the agent's prompt."""

    def __init__(self, memory_dir: Path | str):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _mem(self, agent: str) -> Path:
        return self.dir / f"{agent}.jsonl"

    def _rows(self, agent: str) -> list[dict]:
        p = self._mem(agent)
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def all_lessons(self, agent: str) -> list[str]:
        return [r["lesson"] for r in self._rows(agent)]

    def lessons(self, agent: str) -> list[str]:
        """What goes into the prompt: the MAX_LESSONS_IN_PROMPT most recent, oldest first."""
        return self.all_lessons(agent)[-MAX_LESSONS_IN_PROMPT:]

    def _append(self, agent: str, corrections: list[Correction]) -> list[str]:
        """Store lessons; return the Mubit request ids of the reflection calls that wrote them."""
        ids = []
        with self._mem(agent).open("a") as f:
            for c in corrections:
                rid = c.inputs_snapshot.get("mubit_request_id")
                ids += [rid] if rid else []
                f.write(json.dumps({"correction_id": c.correction_id, "lesson": c.lesson,
                                    "mubit_request_id": rid}) + "\n")
        return ids


class MubitUpdater(LessonMemory, ModelUpdater):
    """Corrections -> versioned lessons in the agent's prompt, with Mubit provenance.

    GAP (checked docs.mubit.ai, Oct 2026): Mubit has no public endpoint for corrections,
    outcomes or ratings, and an adapter can't be called by model id. Mubit learns on its
    side by training per-task adapters from the calls it records (see its console:
    Tasks, Try models). So here a correction becomes a lesson that the next call through
    Mubit uses, and the update ref is the Mubit request id of the reflection call that
    wrote the lesson. If Mubit exposes an outcome API, call it from submit_corrections.
    """

    def __init__(self, memory_dir: Path | str = "agents/memory/mubit", model: str | None = None):
        super().__init__(memory_dir)
        self.model = model or os.environ.get("MUBIT_MODEL") or DEFAULT_MODEL

    def submit_corrections(self, agent, corrections):
        ids = self._append(agent, corrections)
        ref = ",".join(ids) or f"lessons:{agent}:{len(self.all_lessons(agent))}"
        return UpdateRef(agent, ref, fallback=False)

    def get_model_version(self, agent):
        return f"mubit:{self.model}+{agent}-lessons-v{len(self.all_lessons(agent))}"

    def status(self, ref):
        return UpdateStatus("applied", self.get_model_version(ref.agent))


class FakeModelUpdater(LessonMemory, ModelUpdater):
    """FALLBACK ONLY (offline, no Mubit). Same lesson memory; label it in the UI if used."""

    def __init__(self, memory_dir: Path | str = "agents/memory"):
        super().__init__(memory_dir)

    def submit_corrections(self, agent, corrections):
        self._append(agent, corrections)
        return UpdateRef(agent, f"fake:{agent}:{len(self.all_lessons(agent))}", fallback=True)

    def get_model_version(self, agent):
        return f"fallback/{agent}-v{len(self.all_lessons(agent))}"

    def status(self, ref):
        return UpdateStatus("applied", self.get_model_version(ref.agent))


class ScriptedGateway(LLMGateway):
    """Offline gateway for tests and stub-mode dev: a function maps (agent, messages) -> text."""

    def __init__(self, fn: Callable[[str, list[dict]], str]):
        self.fn = fn

    def complete(self, agent, messages, **kw):
        return self.fn(agent, messages)
