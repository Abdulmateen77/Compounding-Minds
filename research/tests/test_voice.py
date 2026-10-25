"""Investor voices: off without a key, cached by voice and text, unknown investors refused (no network)."""
import pytest

from research import voice


class _Client:
    """Stands in for the SDK client: records the calls and returns audio in chunks."""
    def __init__(self):
        self.calls = []
        self.text_to_speech = self

    def convert(self, **kw):
        self.calls.append(kw)
        return iter([b"ID3-", b"mp3"])


def test_off_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert voice.status()["enabled"] is False and "buffett" in voice.status()["voices"]
    with pytest.raises(voice.VoiceError, match="off"):
        voice.speak("buffett", "Hello", cache_dir=tmp_path)


def test_a_line_is_generated_once_then_served_from_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    c = _Client()
    assert voice.speak("munger", "Invert, always invert.", cache_dir=tmp_path, client=c) == b"ID3-mp3"
    assert voice.speak("munger", "Invert,   always invert.", cache_dir=tmp_path, client=c) == b"ID3-mp3"
    assert len(c.calls) == 1 and c.calls[0]["voice_id"] == voice.VOICES["munger"]["voice_id"] and c.calls[0]["model_id"] == "eleven_v4"


def test_every_speaker_has_a_different_voice():
    ids = [v["voice_id"] for v in voice.VOICES.values()]
    assert len(ids) == len(set(ids))


def test_each_investor_can_be_given_another_voice_and_unknown_ones_are_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_VOICE_LYNCH", "my-voice")
    assert voice.voice_for("lynch")["voice_id"] == "my-voice"
    with pytest.raises(voice.VoiceError, match="unknown"):
        voice.speak("graham", "x", cache_dir=tmp_path)
