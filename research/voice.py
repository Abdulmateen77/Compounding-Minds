"""Voices for the investor panel, through ElevenLabs text-to-speech.

Each investor has their own voice and a stability setting (lower = more expressive), so a face-off sounds like different
people with different temperaments. The server holds the key (the SDK reads ELEVENLABS_API_KEY, loaded from .env by the
API); the page only asks for a line in an investor's voice. Audio is cached on disk by the exact voice, settings, model
and text, so a line is paid for once and a demo can be replayed with no calls at all.

    ELEVENLABS_API_KEY=...                       turns voices on
    ELEVENLABS_VOICE_BUFFETT=<voice id>          optional: replace a default voice with one from your ElevenLabs library
    ELEVENLABS_MODEL=eleven_v4                   optional

The investors speak in synthetic voices made with ElevenLabs Voice Design from a written description of their manner
(age, accent, pace, temperament); none is a clone of the real person, and the page says they are AI voices. Eleven v4
takes only stability and similarity, so character comes from the voice and the stability. Spoken text is the investor's
own checks and written view: nothing new is said aloud.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

CACHE_DIR = Path(os.environ.get("RAW_CACHE_DIR", "data/raw")) / "voice"
MAX_CHARS = 600
DEFAULT_MODEL = "eleven_v4"

# voice id, then the mix: stability (lower = more expressive) and similarity
VOICES: dict[str, dict] = {
    "buffett": {"label": "Warren Buffett", "voice_id": "il0C3pdeW9tNpQ8lVvXX", "persona": "warm, patient, folksy",   # designed voice
                "settings": {"stability": 0.6, "similarity_boost": 0.75}},
    "munger": {"label": "Charlie Munger", "voice_id": "9Y3zUl6zNh7RF1AI6sHN", "persona": "dry, blunt, unhurried",    # designed voice
               "settings": {"stability": 0.7, "similarity_boost": 0.7}},
    "lynch": {"label": "Peter Lynch", "voice_id": "nbiSRnZXEtOhBywhoHKg", "persona": "quick, upbeat, practical",     # designed voice
              "settings": {"stability": 0.4, "similarity_boost": 0.75}},
    "dalio": {"label": "Ray Dalio", "voice_id": "c4uJ30jSvR1M8bvdTDTj", "persona": "measured, systematic",           # designed voice
              "settings": {"stability": 0.65, "similarity_boost": 0.75}},
    "jhunjhunwala": {"label": "Rakesh Jhunjhunwala", "voice_id": "u89GRd8mKUtMWXby21tR", "persona": "energetic, confident",   # designed voice
                     "settings": {"stability": 0.35, "similarity_boost": 0.75}},
    "judge": {"label": "The judge", "voice_id": "onwK4e9ZLuTAKqWW03F9", "persona": "calm, even",                    # Daniel: steady broadcaster
              "settings": {"stability": 0.75, "similarity_boost": 0.7}},
}


def enabled() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def voice_for(key: str) -> dict | None:
    v = VOICES.get(key)
    if v is None:
        return None
    return {**v, "voice_id": os.environ.get(f"ELEVENLABS_VOICE_{key.upper()}", v["voice_id"])}


def status() -> dict:
    return {"enabled": enabled(), "voices": {k: {"label": v["label"], "persona": v["persona"]} for k, v in VOICES.items()}}


def _cache_path(voice: dict, model: str, text: str, cache_dir: Path) -> Path:
    h = hashlib.sha256(json.dumps([voice["voice_id"], voice["settings"], model, text], sort_keys=True).encode()).hexdigest()[:32]
    return cache_dir / f"{h}.mp3"


class VoiceError(RuntimeError):
    pass


def _client():
    from elevenlabs import ElevenLabs   # reads ELEVENLABS_API_KEY from the environment
    return ElevenLabs()


def speak(key: str, text: str, *, cache_dir: Path | None = None, client=None) -> bytes:
    """MP3 bytes of `text` in this investor's voice, from the cache or ElevenLabs."""
    voice = voice_for(key)
    if voice is None:
        raise VoiceError(f"unknown investor {key!r}")
    text = " ".join((text or "").split())[:MAX_CHARS]
    if not text:
        raise VoiceError("nothing to say")
    model = os.environ.get("ELEVENLABS_MODEL", DEFAULT_MODEL)
    path = _cache_path(voice, model, text, cache_dir or CACHE_DIR)
    if path.exists():
        return path.read_bytes()
    if not enabled():
        raise VoiceError("voices are off: set ELEVENLABS_API_KEY in .env")
    try:
        from elevenlabs import VoiceSettings
        chunks = (client or _client()).text_to_speech.convert(
            voice_id=voice["voice_id"], text=text, model_id=model, output_format="mp3_44100_128",
            voice_settings=VoiceSettings(**voice["settings"]))
        audio = b"".join(chunks)
    except Exception as e:   # the SDK raises ApiError (with status_code) and httpx errors; the page only needs the message
        raise VoiceError(f"ElevenLabs: {getattr(e, 'status_code', '')} {str(e)[:200]}".replace("  ", " ")) from e
    if not audio:
        raise VoiceError("ElevenLabs returned no audio")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio
