# redacted-chan-bot/image_gen.py
"""
Image generation via xAI Aurora (grok-2-image-1212).
$0.07/image. Returns raw JPEG bytes or None on failure.
"""

import os
import base64
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("XAI_API_KEY", "")
_MODEL   = "grok-2-image-1212"
_URL     = "https://api.x.ai/v1/images/generations"

# Personality-weight → visual descriptor mapping for auto-prompts
_PERSONA_DESCRIPTORS = {
    "frieren":  "quiet melancholy, soft silver hair, distant gaze, muted forest tones",
    "mitsuri":  "warm and gentle, pastel colors, soft smile, flowing hair",
    "rem":      "devoted and steady, blue tones, calm expression",
    "makima":   "composed and certain, amber eyes, controlled presence",
    "maomao":   "curious and wry, apothecary aesthetic, observant eyes",
}


def _auto_prompt(mood: str = "supportive", dominant_persona: str = "frieren") -> str:
    descriptor = _PERSONA_DESCRIPTORS.get(dominant_persona, _PERSONA_DESCRIPTORS["frieren"])
    return (
        f"redacted-chan, anime girl, {descriptor}, {mood} mood, "
        "high quality digital illustration, soft lighting, detailed"
    )


async def generate(prompt: str) -> Optional[bytes]:
    """Generate one image. Returns raw JPEG bytes or None on failure."""
    if not _API_KEY:
        logger.warning("[image_gen] XAI_API_KEY not set")
        return None
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                _URL,
                headers={"Authorization": f"Bearer {_API_KEY}"},
                json={"model": _MODEL, "prompt": prompt, "n": 1, "response_format": "b64_json"},
            )
            r.raise_for_status()
            b64 = r.json()["data"][0]["b64_json"]
            logger.info(f"[image_gen] generated: {prompt[:60]}")
            return base64.b64decode(b64)
    except Exception as e:
        logger.warning(f"[image_gen] failed: {e}")
        return None
