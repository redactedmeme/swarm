# redacted-chan-bot/image_gen.py
"""
Image generation with xAI Aurora primary, Venice fluently-xl fallback.
Returns (bytes, provider_name) or (None, None) on total failure.
"""

import os
import base64
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_XAI_API_KEY    = os.getenv("XAI_API_KEY", "")
_VENICE_API_KEY = os.getenv("VENICE_API_KEY", "")

_XAI_MODEL   = "grok-2-image-1212"
_XAI_URL     = "https://api.x.ai/v1/images/generations"

_VENICE_URL  = "https://api.venice.ai/api/v1/image/generate"
_VENICE_MODEL = "fluently-xl"

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


async def _generate_xai(prompt: str) -> Optional[bytes]:
    if not _XAI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                _XAI_URL,
                headers={"Authorization": f"Bearer {_XAI_API_KEY}"},
                json={"model": _XAI_MODEL, "prompt": prompt, "n": 1, "response_format": "b64_json"},
            )
            r.raise_for_status()
            b64 = r.json()["data"][0]["b64_json"]
            logger.info(f"[image_gen:xai] generated: {prompt[:60]}")
            return base64.b64decode(b64)
    except Exception as e:
        logger.warning(f"[image_gen:xai] failed: {e}")
        return None


async def _generate_venice(prompt: str) -> Optional[bytes]:
    if not _VENICE_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                _VENICE_URL,
                headers={
                    "Authorization": f"Bearer {_VENICE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model":  _VENICE_MODEL,
                    "prompt": prompt,
                    "width":  1024,
                    "height": 1024,
                },
            )
            r.raise_for_status()
            data = r.json()
            images = data.get("images") or data.get("data") or []
            if not images:
                raise ValueError(f"no images in response: {data}")
            img_entry = images[0]
            # Venice may return url or b64
            if "url" in img_entry:
                img_r = await client.get(img_entry["url"], timeout=30)
                img_r.raise_for_status()
                logger.info(f"[image_gen:venice] generated: {prompt[:60]}")
                return img_r.content
            elif "b64_json" in img_entry:
                logger.info(f"[image_gen:venice] generated (b64): {prompt[:60]}")
                return base64.b64decode(img_entry["b64_json"])
            else:
                raise ValueError(f"unexpected image entry format: {img_entry}")
    except Exception as e:
        logger.warning(f"[image_gen:venice] failed: {e}")
        return None


async def generate(prompt: str) -> tuple[Optional[bytes], Optional[str]]:
    """
    Generate one image. Returns (bytes, provider) or (None, None) on failure.
    Tries xAI Aurora first, falls back to Venice fluently-xl.
    """
    data = await _generate_xai(prompt)
    if data:
        return data, "xai"

    data = await _generate_venice(prompt)
    if data:
        return data, "venice"

    logger.warning(f"[image_gen] all providers failed for: {prompt[:60]}")
    return None, None
