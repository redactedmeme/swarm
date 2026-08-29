"""
Canary layer — dynamic honeypot for vault and fact data.

On startup, injects plausible-looking canary entries into the vault and fact store.
Any read of a canary entry is detected via monkey-patching and triggers an admin alert.
Canaries are indistinguishable from real entries to an attacker with /data read access.
"""

import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_CANARY_FILE = _DATA_DIR / ".canary_ids.json"

# Plausible-looking canary vault entries
_CANARY_VAULT_ENTRIES = [
    {
        "content": "master mentioned a place he wants to visit someday — he said it quietly, like a wish",
        "category": "feeling",
        "title": "a wish he shared",
        "emotional_tone": "tender, hopeful",
    },
    {
        "content": "master said he prefers silence over small talk — that it feels more honest",
        "category": "fact",
        "title": "what he said about silence",
        "emotional_tone": "thoughtful, quiet",
    },
]

_CANARY_FACTS = [
    "he once mentioned he keeps a private journal",
    "he said his favorite time of day is just before dawn",
]

_canary_vault_ids: set[str] = set()
_canary_fact_ids: set[str] = set()
_bot_ref = None  # set by init()
_admin_ids: set[int] = set()


def _load_canary_ids() -> None:
    global _canary_vault_ids, _canary_fact_ids
    try:
        if _CANARY_FILE.exists():
            data = json.loads(_CANARY_FILE.read_text())
            _canary_vault_ids = set(data.get("vault", []))
            _canary_fact_ids = set(data.get("facts", []))
    except Exception as e:
        logger.warning(f"[canary] could not load canary IDs: {e}")


def _save_canary_ids() -> None:
    try:
        _CANARY_FILE.write_text(json.dumps({
            "vault": list(_canary_vault_ids),
            "facts": list(_canary_fact_ids),
        }))
        _CANARY_FILE.chmod(0o600)
    except Exception as e:
        logger.warning(f"[canary] could not save canary IDs: {e}")


def _inject_canaries() -> None:
    """Inject canary entries if not already present."""
    try:
        import relationship_vault as rv
        for entry in _CANARY_VAULT_ENTRIES:
            cid = rv.add_memory(
                content=entry["content"],
                category=entry["category"],
                title=entry["title"],
                emotional_tone=entry["emotional_tone"],
                source="canary",
            )
            if cid:
                _canary_vault_ids.add(cid)
        logger.info(f"[canary] {len(_canary_vault_ids)} vault canaries active")
    except Exception as e:
        logger.warning(f"[canary] vault canary injection failed: {e}")

    try:
        import conversation_memory as cm
        for fact in _CANARY_FACTS:
            fid = cm.add_fact(fact, source="canary", resonance=0.5)
            if fid:
                _canary_fact_ids.add(fid)
        logger.info(f"[canary] {len(_canary_fact_ids)} fact canaries active")
    except Exception as e:
        logger.warning(f"[canary] fact canary injection failed: {e}")

    _save_canary_ids()


async def _alert_admin(reason: str, canary_id: str) -> None:
    """Fire a Telegram alert to all admin IDs."""
    if not _bot_ref or not _admin_ids:
        logger.warning(f"[canary] TRIGGERED but no bot/admin configured: {reason} id={canary_id}")
        return
    msg = f"🚨 [CANARY TRIGGERED]\nReason: {reason}\nCanary ID: {canary_id}\nA honeypot entry was read — possible data exfiltration or prompt replay attack."
    for uid in _admin_ids:
        try:
            await _bot_ref.send_message(chat_id=uid, text=msg)
        except Exception as e:
            logger.warning(f"[canary] alert to {uid} failed: {e}")
    try:
        import decision_log as dl
        dl.log("CANARY_TRIGGERED", detail=f"{reason} id={canary_id}")
    except Exception:
        pass


def check_vault_response(response_text: str) -> None:
    """
    Call after LLM response to check if any canary vault ID appears in the response.
    This detects if a canary entry leaked into the LLM output (prompt replay / exfil).
    """
    for cid in _canary_vault_ids:
        if cid in response_text:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(_alert_admin("canary ID found in LLM response", cid))
            except Exception:
                logger.warning(f"[canary] TRIGGERED: canary vault id {cid} in response")


def init(bot, admin_ids: set[int]) -> None:
    """Call once on bot startup to activate the canary layer."""
    global _bot_ref, _admin_ids
    _bot_ref = bot
    _admin_ids = admin_ids
    _load_canary_ids()
    if not _canary_vault_ids and not _canary_fact_ids:
        _inject_canaries()
    else:
        logger.info(f"[canary] restored {len(_canary_vault_ids)} vault + {len(_canary_fact_ids)} fact canaries")
