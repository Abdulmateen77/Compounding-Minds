"""Banyan Sapling client: verify a claim against a policy and evidence (Mubit's verifier model).

Used by the grader only for text judgements that keyword rules get wrong (going-concern
language). Every verdict is cached on disk, so a replay never calls the endpoint twice and
the demo can run with replay_only=True (CLAUDE.md rule 5: no live calls in the demo).

Endpoint: Mubit's Hugging Face inference endpoint (Night Shift quickstart, no auth).
Request:  POST {"inputs": {"policy", "evidence", "claim"}}
Reply:    {"status", "raw_label", "prediction_set", "probabilities", ...}
          labels: supported | violation | insufficient_information | inconsistent_context
          status may also be "unsure" when the calibrated prediction set has several labels.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_URL = "https://6adbee0669a00298cd4774c9.endpoints.huggingface.cloud"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "sapling_cache"
LABELS = ("supported", "violation", "insufficient_information", "inconsistent_context")


class SaplingError(RuntimeError):
    """The endpoint failed or replied in a shape we don't understand. Never cached."""


class CacheMiss(SaplingError):
    """replay_only=True and this input has no saved verdict."""


@dataclass(frozen=True)
class Verdict:
    status: str                       # a label from LABELS, or "unsure"
    raw_label: str                    # highest-probability label
    prediction_set: tuple[str, ...]
    probabilities: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_reply(cls, data: dict) -> "Verdict":
        if not isinstance(data, dict) or data.get("error"):
            raise SaplingError(f"Sapling error: {data.get('error') if isinstance(data, dict) else data!r}")
        try:
            v = cls(status=str(data["status"]), raw_label=str(data["raw_label"]),
                    prediction_set=tuple(data.get("prediction_set") or ()),
                    probabilities={k: float(p) for k, p in (data.get("probabilities") or {}).items()})
        except (KeyError, TypeError, ValueError) as e:
            raise SaplingError(f"unexpected Sapling reply: {e}") from e
        if v.raw_label not in LABELS:
            raise SaplingError(f"unknown Sapling label {v.raw_label!r}")
        return v

    def as_dict(self) -> dict:
        return {"status": self.status, "raw_label": self.raw_label,
                "prediction_set": list(self.prediction_set), "probabilities": self.probabilities}


class SaplingClient:
    def __init__(self, url: str | None = None, cache_dir: Path | str | None = None,
                 replay_only: bool = False, timeout: float = 60.0, post=None):
        self.url = url or os.environ.get("SAPLING_URL") or DEFAULT_URL
        self.dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.replay_only, self.timeout = replay_only, timeout
        self._post = post or self._http_post  # tests pass a fake
        self.hits = self.misses = 0

    @staticmethod
    def key_for(policy: str, evidence: str, claim: str) -> str:
        blob = json.dumps({"v": 1, "policy": policy, "evidence": evidence, "claim": claim},
                          sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def verify(self, policy: str, evidence: str, claim: str) -> Verdict:
        if not (policy.strip() and evidence.strip() and claim.strip()):
            raise SaplingError("policy, evidence and claim must all be nonempty")
        key = self.key_for(policy, evidence, claim)
        path = self.dir / f"{key}.json"
        if path.exists():
            self.hits += 1
            return Verdict.from_reply(json.loads(path.read_text())["reply"])
        if self.replay_only:
            raise CacheMiss(f"no saved Sapling verdict (key {key[:12]}); replay_only forbids a live call")
        reply = self._post({"inputs": {"policy": policy, "evidence": evidence, "claim": claim}})
        verdict = Verdict.from_reply(reply)  # raises before caching if the reply is bad
        self.misses += 1
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"key": key, "url": self.url, "reply": reply,
                                   "saved_at": int(time.time())}, ensure_ascii=False))
        tmp.replace(path)  # atomic
        return verdict

    def _http_post(self, payload: dict) -> dict:
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise SaplingError(f"Sapling HTTP {e.code}: {e.read()[:300]!r}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise SaplingError(f"Sapling request failed: {e}") from e
