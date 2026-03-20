"""ElevenLabs TTS voice generation.

Generates speech audio from text for YouTube Shorts voiceover.
Returns path to an MP3 file.
"""

import time
from pathlib import Path

import requests

from src.config import (
    DATA_DIR,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL,
)

VOICE_DIR = DATA_DIR / "voice_cache"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

# Voice settings tuned for authoritative motivational delivery:
#   stability=0.35  → more expressive, less monotone
#   similarity=0.85 → stay close to the voice character
#   style=0.6       → push toward intense/commanding delivery
VOICE_SETTINGS = {
    "stability": 0.35,
    "similarity_boost": 0.85,
    "style": 0.6,
}


def generate_voiceover(text: str, filename: str | None = None) -> Path:
    """Generate speech audio from text via ElevenLabs API.

    Args:
        text: The quote/text to speak.
        filename: Optional output filename. Auto-generated if None.

    Returns:
        Path to the generated MP3 file.

    Raises:
        RuntimeError: If API call fails or no API key configured.
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError(
            "ELEVENLABS_API_KEY not set. Add it to .env file."
        )

    if not filename:
        filename = f"voice_{int(time.time())}.mp3"

    output_path = VOICE_DIR / filename

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

    response = requests.post(
        url,
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": VOICE_SETTINGS,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"ElevenLabs API error {response.status_code}: "
            f"{response.text[:300]}"
        )

    output_path.write_bytes(response.content)
    return output_path
