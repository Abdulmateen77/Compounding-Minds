"""Voices for the investor panel, through ElevenLabs text-to-speech. The foundation: off until a key is set.

Each investor has a voice and a "mix" (how steady, how expressive, how fast), so a face-off sounds like two people. The
server holds the key; the page only asks for a line in an investor's voice. Audio is cached on disk by the exact voice,
mix and text, so a line is paid for once and a demo can be replayed with no calls at all.

    ELEVENLABS_API_KEY=...                       turns voices on
    ELEVENLABS_VOICE_BUFFETT=<voice id>          optional: replace a default voice with one from your ElevenLabs library
    ELEVENLABS_MODEL=eleven_multilingual_v2      optional

The default voice ids are ElevenLabs' long-standing premade voices; if your account does not have one, set the variable for
that investor. Spoken text is the investor's own checks and written view: nothing new is said aloud.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
CACHE_DIR = Path(os.environ.get("RAW_CACHE_DIR", "data/raw")) / "voice"
MAX_CHARS = 600

# voice id, then the mix: stability (lower = more expressive), similarity, style, speed
VOICES: dict[str, dict] = {
    "buffett": {"label": "Warren Buffett", "voice_id": "pNInz6obpgDQGcFmaJgB", "persona": "warm, patient, folksy",
                "settings": {"stability": 0.6, "similarity_boost": 0.75, "style": 0.25, "use_speaker_boost": True, "speed": 0.95}},
    "munger": {"label": "Charlie Munger", "voice_id": "VR6AewLTigWG4xSOukaG", "persona": "dry, blunt, unhurried",
               "settings": {"stability": 0.7, "similarity_boost": 0.7, "style": 0.15, "use_speaker_boost": True, "speed": 0.9}},
    "lynch": {"label": "Peter Lynch", "voice_id": "TxGEqnHWrfWFTfGW9XjX", "persona": "quick, upbeat, practical",
              "settings": {"stability": 0.45, "similarity_boost": 0.75, "style": 0.45, "use_speaker_boost": True, "speed": 1.05}},
    "dalio": {"label": "Ray Dalio", "voice_id": "ErXwobaYiN019PkySvjV", "persona": "measured, systematic",
              "settings": {"stability": 0.65, "similarity_boost": 0.75, "style": 0.2, "use_speaker_boost": True, "speed": 1.0}},
    "jhunjhunwala": {"label": "Rakesh Jhunjhunwala", "voice_id": "yoZ06aMxZJJ28mfd3POQ", "persona": "energetic, confident",
                     "settings": {"stability": 0.4, "similarity_boost": 0.75, "style": 0.5, "use_speaker_boost": True, "speed": 1.05}},
    "judge": {"label": "The judge", "voice_id": "onwK4e9ZLuTAKqWW03F9", "persona": "calm, even",
              "settings": {"stability": 0.75, "similarity_boost": 0.7, "style": 0.1, "use_speaker_boost": True, "speed": 0.95}},
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


def speak(key: str, text: str, *, cache_dir: Path | None = None, opener=urllib.request.urlopen) -> bytes:
    """MP3 bytes of `text` in this investor's voice, from the cache or ElevenLabs."""
    voice = voice_for(key)
    if voice is None:
        raise VoiceError(f"unknown investor {key!r}")
    text = " ".join((text or "").split())[:MAX_CHARS]
    if not text:
        raise VoiceError("nothing to say")
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    path = _cache_path(voice, model, text, cache_dir or CACHE_DIR)
    if path.exists():
        return path.read_bytes()
    if not enabled():
        raise VoiceError("voices are off: set ELEVENLABS_API_KEY in .env")
    settings = dict(voice["settings"])
    speed = settings.pop("speed", None)
    body = {"text": text, "model_id": model, "voice_settings": {**settings, **({"speed": speed} if speed else {})}}
    req = urllib.request.Request(API.format(voice=voice["voice_id"]), data=json.dumps(body).encode(), method="POST",
                                 headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json",
                                          "Accept": "audio/mpeg"})
    try:
        with opener(req, timeout=60) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        raise VoiceError(f"ElevenLabs said {e.code}: {e.read()[:200].decode(errors='ignore')}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise VoiceError(f"could not reach ElevenLabs: {e}") from e
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio
