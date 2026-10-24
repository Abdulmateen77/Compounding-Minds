"""A reply cut off at max_tokens must never be returned or cached (found on the first live replay)."""
from types import SimpleNamespace

import pytest

from agents.gateway import MubitGateway


class _Raw:
    def __init__(self, text, stop):
        self.headers = {"x-middleware-request-id": "mreq_x"}
        self._msg = SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                                    usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    def parse(self):
        return self._msg


class _Client:
    def __init__(self, replies):
        self.calls, self._replies = [], list(replies)
        self.messages = SimpleNamespace(with_raw_response=SimpleNamespace(create=self._create))

    def _create(self, **params):
        self.calls.append(params)
        return _Raw(*self._replies.pop(0))


MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_a_cut_off_reply_is_retried_with_a_bigger_budget_and_the_complete_one_is_returned():
    c = _Client([('{"half', "max_tokens"), ('{"whole": 1}', "end_turn")])
    out = MubitGateway(client=c, model="m", max_tokens=1000).complete("fundamentals", MSGS)
    assert out == '{"whole": 1}'
    assert [p["max_tokens"] for p in c.calls] == [1000, 2000]


def test_a_reply_that_is_still_cut_off_raises_instead_of_being_returned():
    c = _Client([('{"half', "max_tokens"), ('{"still half', "max_tokens")])
    with pytest.raises(RuntimeError, match="cut off"):
        MubitGateway(client=c, model="m").complete("fundamentals", MSGS)


def test_thinking_is_off_by_default_and_can_be_turned_on(monkeypatch):
    monkeypatch.delenv("MUBIT_THINKING", raising=False)
    c = _Client([("ok", "end_turn")])
    MubitGateway(client=c, model="m").complete("risk", MSGS)
    assert c.calls[0]["thinking"] == {"type": "disabled"}
    monkeypatch.setenv("MUBIT_THINKING", "1")
    c2 = _Client([("ok", "end_turn")])
    MubitGateway(client=c2, model="m").complete("risk", MSGS)
    assert "thinking" not in c2.calls[0]


def test_the_default_output_budget_leaves_room():
    assert MubitGateway(client=_Client([]), model="m").max_tokens >= 2048


def test_old_cache_entries_from_before_the_fix_no_longer_match(tmp_path):
    """Replies cached while the cap was 1024 are cut off; the cache key moved to v2 so they are never reused."""
    import hashlib
    import json
    from agents.cache import CachingGateway
    gw = CachingGateway(MubitGateway(client=_Client([]), model="m"), cache_dir=tmp_path)
    old = {"v": 1, "model": "m", "agent": "risk", "messages": MSGS, "params": {}}
    old_key = hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    assert gw.key_for("risk", MSGS) != old_key
