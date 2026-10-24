"""Reply cache: the same prompt is never paid for twice (README 8.1, CLAUDE.md rule 5).

Wrap any gateway:   gw = CachingGateway(MubitGateway())

* hit  -> returns the saved reply, no network, no cost, and nothing reaches Mubit
* miss -> calls the real gateway, saves the reply
* replay_only=True -> a miss raises CacheMiss: the demo can prove it makes no live calls
* refresh=True     -> ignore saved replies and call live again (overwrites them)

The key covers the model, the model version (if a version_fn is given), the agent, the messages and any option that changes the reply
(max_tokens, ...). It ignores `session_id` and `purpose`, which are only labels for Mubit.
A cached reply keeps the Mubit request id of the call that produced it, so lessons stay
traceable in Mubit's console. Failed calls are never cached.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable

from .gateway import LLMGateway

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "llm_cache"
_LABEL_ONLY = {"session_id", "purpose"}


class CacheMiss(RuntimeError):
    """Raised in replay_only mode when a prompt has no saved reply."""


class CachingGateway(LLMGateway):
    def __init__(self, inner: LLMGateway, cache_dir: Path | str | None = None,
                 replay_only: bool = False, refresh: bool = False,
                 version_fn: Callable[[str], str] | None = None):
        # version_fn(agent) -> the agent's current model version (e.g. updater.get_model_version).
        # It is part of the key, so a model update makes every older entry stop matching.
        self.version_fn = version_fn
        self.inner = inner
        self.dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.replay_only, self.refresh = replay_only, refresh
        self.hits = 0
        self.misses = 0
        self.last_request_id: str | None = None

    # The loop and batch scripts read these off whatever gateway they were given.
    @property
    def model(self) -> str:
        return getattr(self.inner, "model", type(self.inner).__name__)

    @property
    def requests(self) -> list:
        return getattr(self.inner, "requests", [])

    def key_for(self, agent: str, messages: list[dict], **kw) -> str:
        payload = {"v": 1, "model": self.model, "agent": agent, "messages": messages,
                   "params": {k: v for k, v in sorted(kw.items()) if k not in _LABEL_ONLY}}
        if self.version_fn is not None:  # absent unless used, so existing keys stay valid
            payload["model_version"] = self.version_fn(agent)
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def has(self, agent: str, messages: list[dict], **kw) -> bool:
        return self._path(self.key_for(agent, messages, **kw)).exists()

    def complete(self, agent, messages, **kw):
        key = self.key_for(agent, messages, **kw)
        path = self._path(key)
        if path.exists() and not self.refresh:
            entry = json.loads(path.read_text())
            self.hits += 1
            self.last_request_id = entry.get("mubit_request_id")
            return entry["text"]
        if self.replay_only:
            raise CacheMiss(f"no saved reply for {agent} (key {key[:12]}); replay_only forbids a live call")
        text = self.inner.complete(agent, messages, **kw)  # exceptions pass through and are not cached
        self.misses += 1
        self.last_request_id = getattr(self.inner, "last_request_id", None)
        entry = {"key": key, "agent": agent, "model": self.model, "text": text,
                 "mubit_request_id": self.last_request_id, "saved_at": int(time.time())}
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False))
        tmp.replace(path)  # atomic: a crash never leaves a half-written reply
        return text
