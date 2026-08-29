"""
SOUL.md backup and restore.

Keeps daily snapshots in /data/soul_backups/ (rolling 7 days).
On startup, if /data/SOUL.md is missing but a backup exists, auto-restores
from the most recent backup so a volume wipe doesn't erase her evolved soul.
"""

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR   = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
SOUL_PATH   = _DATA_DIR / "SOUL.md"
_SOUL_SEED  = Path(__file__).resolve().parent / "SOUL.md"
_BACKUP_DIR = _DATA_DIR / "soul_backups"
_MAX_BACKUPS = 7


def backup_soul() -> bool:
    """Save a dated snapshot of SOUL.md. Returns True if backup was made."""
    if not SOUL_PATH.exists():
        return False
    try:
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        dest = _BACKUP_DIR / f"SOUL_{today}.md"
        shutil.copy2(SOUL_PATH, dest)
        try:
            dest.chmod(0o600)
        except Exception:
            pass
        _prune_old_backups()
        logger.info(f"[soul_backup] saved snapshot: {dest.name}")
        return True
    except Exception as e:
        logger.warning(f"[soul_backup] backup failed: {e}")
        return False


def _prune_old_backups() -> None:
    try:
        backups = sorted(_BACKUP_DIR.glob("SOUL_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[_MAX_BACKUPS:]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def restore_if_missing() -> bool:
    """
    If SOUL.md is missing from /data, restore from most recent backup.
    Falls back to seed file if no backups exist.
    Returns True if a restore was performed.
    """
    if SOUL_PATH.exists():
        return False

    # Try most recent backup first
    try:
        backups = sorted(_BACKUP_DIR.glob("SOUL_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if backups:
            shutil.copy2(backups[0], SOUL_PATH)
            try:
                SOUL_PATH.chmod(0o600)
            except Exception:
                pass
            logger.warning(f"[soul_backup] SOUL.md was missing — restored from backup {backups[0].name}")
            return True
    except Exception as e:
        logger.warning(f"[soul_backup] backup restore failed: {e}")

    # Fall back to seed
    if _SOUL_SEED.exists():
        shutil.copy2(_SOUL_SEED, SOUL_PATH)
        try:
            SOUL_PATH.chmod(0o600)
        except Exception:
            pass
        logger.warning("[soul_backup] SOUL.md was missing — restored from repo seed (no backup found)")
        return True

    return False


def get_latest_backup_path() -> Path | None:
    """Return the most recent backup path, or None if none exist."""
    try:
        backups = sorted(_BACKUP_DIR.glob("SOUL_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return backups[0] if backups else None
    except Exception:
        return None
