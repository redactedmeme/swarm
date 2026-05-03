# redacted-chan-bot/image_store.py
"""
Persistent image storage for generated images.
Saves JPEG files to /data/images/ and maintains an append-only JSONL log.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR   = Path(os.getenv("DATA_DIR", "/data"))
_IMAGES_DIR = _DATA_DIR / "images"
_LOG_PATH   = _DATA_DIR / "image_log.jsonl"


def _ensure_dirs() -> None:
    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def save_image(
    data: bytes,
    prompt: str,
    persona: str = "frieren",
    mood: str = "supportive",
    vault_ref: Optional[str] = None,
    provider: str = "xai",
) -> str:
    """Save image bytes to disk and append a log entry. Returns image_id."""
    _ensure_dirs()
    image_id = str(uuid.uuid4())[:8]
    path = _IMAGES_DIR / f"{image_id}.jpg"
    path.write_bytes(data)

    entry = {
        "id":        image_id,
        "ts":        datetime.now(timezone.utc).isoformat(),
        "prompt":    prompt[:200],
        "persona":   persona,
        "mood":      mood,
        "vault_ref": vault_ref,
        "provider":  provider,
        "size_kb":   round(len(data) / 1024, 1),
    }
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info(f"[image_store] saved {image_id} ({entry['size_kb']}KB) via {provider}")
    return image_id


def list_images(n: int = 10) -> list[dict]:
    """Return the n most recent image log entries (newest first)."""
    if not _LOG_PATH.exists():
        return []
    lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
        if len(entries) >= n:
            break
    return entries


def get_image_path(image_id: str) -> Optional[Path]:
    """Return Path to image file, or None if not found."""
    path = _IMAGES_DIR / f"{image_id}.jpg"
    return path if path.exists() else None


def link_vault_ref(image_id: str, vault_ref: str) -> bool:
    """Update vault_ref for an existing log entry (rewrites log). Returns True if found."""
    if not _LOG_PATH.exists():
        return False
    lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("id") == image_id:
                entry["vault_ref"] = vault_ref
                updated = True
            new_lines.append(json.dumps(entry))
        except json.JSONDecodeError:
            new_lines.append(line)
    if updated:
        _LOG_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return updated
