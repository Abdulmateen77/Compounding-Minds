"""Investor voices: off without a key, cached by voice and text, unknown investors refused (no network)."""
import io

import pytest

from research import voice


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_off_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert voice.status()["enabled"] is False and "buffett" in voice.status()["voices"]
    with pytest.raises(voice.VoiceError, match="off"):
        voice.speak("buffett", "Hello", cache_dir=tmp_path)


def test_a_line_is_generated_once_then_served_from_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    calls = []

    def opener(req, timeout):
        calls.append((req.full_url, req.headers.get("Xi-api-key")))
        return _Resp(b"ID3-mp3")
    assert voice.speak("munger", "Invert, always invert.", cache_dir=tmp_path, opener=opener) == b"ID3-mp3"
    assert voice.speak("munger", "Invert,   always invert.", cache_dir=tmp_path, opener=opener) == b"ID3-mp3"
    assert len(calls) == 1 and calls[0][1] == "k" and voice.VOICES["munger"]["voice_id"] in calls[0][0]


def test_each_investor_can_be_given_another_voice_and_unknown_ones_are_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_VOICE_LYNCH", "my-voice")
    assert voice.voice_for("lynch")["voice_id"] == "my-voice"
    with pytest.raises(voice.VoiceError, match="unknown"):
        voice.speak("graham", "x", cache_dir=tmp_path)
