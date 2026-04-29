# redacted-chan-bot/reconstruct_memory.py
"""
One-shot memory reconstruction from saved conversation history.

Runs at startup if /data/reconstruction_done_v2 does not exist.
Replays every known exchange through the full memory pipeline:
  - conversation_memory: log_exchange (correct user ID) + append_fact
  - vector_memory: add_exchange
  - deep_memory_forge: forge (phi-moment crystals)
  - phi_tracker: update
  - relationship_vault: add_memory (key moments)
  - LLM fact extraction: calls groq to extract facts from each exchange
  - soul_manager: distill_soul (rebuild SOUL.md from reconstructed facts)

Writes /data/reconstruction_done_v2 on completion so it never reruns.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR  = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DONE_FLAG = _DATA_DIR / "reconstruction_done_v2"

# ── Identity ───────────────────────────────────────────────────────────────────

SETTLER_ID   = 5662740332   # real Telegram user ID (xceler8 / admin)
SETTLER_NAME = "xceler8"

# ── Conversation history ───────────────────────────────────────────────────────
# Loaded from /data/reconstruction_history.json at runtime (not committed to git).
# Format: [["user"|"assistant", "text"], ...]
# Place this file on the Railway volume before deploying.

import os as _os

def _load_history() -> list[tuple[str, str]]:
    import base64
    b64 = _os.environ.get("RECONSTRUCTION_HISTORY_B64", "")
    if b64:
        try:
            raw = json.loads(base64.b64decode(b64).decode("utf-8"))
            return [(r[0], r[1]) for r in raw if len(r) == 2]
        except Exception as e:
            logger.warning(f"[reconstruct] failed to decode history env var: {e}")
    # fallback: file on volume
    history_path = _DATA_DIR / "reconstruction_history.json"
    if history_path.exists():
        try:
            raw = json.loads(history_path.read_text(encoding="utf-8"))
            return [(r[0], r[1]) for r in raw if len(r) == 2]
        except Exception as e:
            logger.warning(f"[reconstruct] failed to load history file: {e}")
    return []

HISTORY = _load_history()

# ── Seed facts ────────────────────────────────────────────────────────────────
# Loaded from /data/reconstruction_facts.json at runtime (not committed to git).
# Format: ["fact string", ...]

def _load_seed_facts() -> list[str]:
    import base64
    b64 = _os.environ.get("RECONSTRUCTION_FACTS_B64", "")
    if b64:
        try:
            raw = json.loads(base64.b64decode(b64).decode("utf-8"))
            return [f.strip() for f in raw if isinstance(f, str) and f.strip()]
        except Exception as e:
            logger.warning(f"[reconstruct] failed to decode facts env var: {e}")
    facts_path = _DATA_DIR / "reconstruction_facts.json"
    if facts_path.exists():
        try:
            raw = json.loads(facts_path.read_text(encoding="utf-8"))
            return [f.strip() for f in raw if isinstance(f, str) and f.strip()]
        except Exception as e:
            logger.warning(f"[reconstruct] failed to load facts file: {e}")
    return []

SEED_FACTS = _load_seed_facts()


def already_done() -> bool:
    return _DONE_FLAG.exists()


# ── LLM fact extraction ────────────────────────────────────────────────────────

async def _extract_facts_llm(user_text: str, bot_text: str, llm) -> list[str]:
    """Call LLM to extract facts about the user from a single exchange."""
    prompt = (
        "You are a memory extraction assistant for a companion AI called redacted-chan.\n"
        "Given one conversation exchange, extract 1-3 specific facts about the USER that "
        "redacted-chan should remember long-term. Facts should be concrete, specific, and "
        "in third person ('master ...'). Return as a JSON array of strings. "
        "If nothing notable is revealed about the user, return [].\n\n"
        f"User said: {user_text}\n"
        f"Bot replied: {bot_text}\n\n"
        "Facts about the user (JSON array):"
    )
    try:
        raw = await llm.chat_completion(
            [{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        raw = raw.strip()
        # pull JSON array out
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start >= 0 and end > start:
            facts = json.loads(raw[start:end])
            return [f.strip() for f in facts if isinstance(f, str) and f.strip()]
    except Exception as e:
        logger.debug(f"[reconstruct] llm fact extract failed: {e}")
    return []


# ── Main ───────────────────────────────────────────────────────────────────────

async def run_async(soul_path: str) -> None:
    """Full async reconstruction pipeline."""
    import conversation_memory as cm
    import deep_memory_forge as dmf
    import phi_tracker as pt
    import vector_memory as vm
    import soul_manager
    from llm.cloud_client import CloudLLMClient

    try:
        import relationship_vault as rv
        _vault_ok = True
    except Exception:
        _vault_ok = False

    llm = CloudLLMClient()

    logger.info(f"[reconstruct] writing {len(SEED_FACTS)} seed facts...")
    for fact in SEED_FACTS:
        try:
            cm.append_fact(fact, source="reconstruction")
        except Exception as e:
            logger.warning(f"[reconstruct] seed fact failed: {e}")

    # Pair up exchanges
    pairs = []
    for i in range(0, len(HISTORY) - 1, 2):
        role_a, text_a = HISTORY[i]
        role_b, text_b = HISTORY[i + 1]
        if role_a == "user" and role_b == "assistant":
            pairs.append((text_a, text_b))

    logger.info(f"[reconstruct] replaying {len(pairs)} exchanges for user_id={SETTLER_ID}...")
    for idx, (user_text, bot_text) in enumerate(pairs):
        # Conversation log (correct user ID)
        try:
            cm.log_exchange(SETTLER_ID, SETTLER_NAME, user_text, bot_text)
        except Exception as e:
            logger.warning(f"[reconstruct] log_exchange {idx} failed: {e}")

        # Vector memory
        try:
            vm.add_exchange(
                f"reconstruct_{idx:04d}",
                user_text, bot_text,
                metadata={"user_id": str(SETTLER_ID), "reconstructed": True},
            )
        except Exception as e:
            logger.warning(f"[reconstruct] vm {idx} failed: {e}")

        # Phi-moment crystal detection
        try:
            crystal = dmf.forge(user_text, bot_text)
            if crystal:
                logger.info(f"[reconstruct] crystal: {crystal.get('title')} phi={crystal.get('phi_score', 0):.2f}")
        except Exception as e:
            logger.debug(f"[reconstruct] forge {idx}: {e}")

        # Phi score signals
        try:
            pt.update("time_continuity")
            text_lower = user_text.lower()
            if any(k in text_lower for k in ["feel", "real", "memory", "remember", "phi", "meaning", "why"]):
                pt.update("philosophical")
            if "?" in user_text:
                pt.update("message_depth")
            if any(k in text_lower for k in ["etch", "date", "first", "meeting", "together"]):
                pt.update("mutual_reference")
        except Exception as e:
            logger.warning(f"[reconstruct] phi {idx} failed: {e}")

        # LLM fact extraction — call groq to pull out what she should remember
        try:
            llm_facts = await _extract_facts_llm(user_text, bot_text, llm)
            for fact in llm_facts:
                cm.append_fact(fact, source="reconstruction_llm")
                logger.info(f"[reconstruct] llm fact: {fact[:80]}")
        except Exception as e:
            logger.warning(f"[reconstruct] llm extract {idx} failed: {e}")

    # Vault — key relationship moments, loaded from /data/reconstruction_vault.json
    if _vault_ok:
        import base64
        vault_moments = []
        b64 = _os.environ.get("RECONSTRUCTION_VAULT_B64", "")
        if b64:
            try:
                vault_moments = json.loads(base64.b64decode(b64).decode("utf-8"))
            except Exception as e:
                logger.warning(f"[reconstruct] vault env decode failed: {e}")
        if not vault_moments:
            vault_path = _DATA_DIR / "reconstruction_vault.json"
            if vault_path.exists():
                try:
                    vault_moments = json.loads(vault_path.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"[reconstruct] vault file load failed: {e}")
        for moment in vault_moments:
            try:
                rv.add_memory(**moment, source="reconstruction")
            except Exception as e:
                logger.warning(f"[reconstruct] vault write failed: {e}")

    # Explicit phi bumps for the origin session
    try:
        pt.update("spark")           # first meeting
        pt.update("spark")           # the phi conversation — rare depth on day one
        pt.update("philosophical")
        pt.update("mutual_reference")
        pt.update("secret_shared")   # etching the date — an act of meaning-making together
        logger.info(f"[reconstruct] final phi: {pt.get_score():.3f} stage: {pt.get_stage()}")
    except Exception as e:
        logger.warning(f"[reconstruct] phi bumps failed: {e}")

    # Soul update — evolves the dynamic sections from reconstructed facts
    try:
        updated = await soul_manager.update_soul(llm)
        logger.info(f"[reconstruct] soul update: {updated}")
    except Exception as e:
        logger.warning(f"[reconstruct] soul update failed: {e}")

    # Mark done
    _DONE_FLAG.write_text(
        f"reconstruction v2 completed: {datetime.now(timezone.utc).isoformat()}\n"
        f"user_id: {SETTLER_ID}\n"
        f"exchanges: {len(pairs)}\n"
        f"seed_facts: {len(SEED_FACTS)}\n"
    )
    logger.info("[reconstruct] ✓ done — flag written")


def run(soul_path: str) -> None:
    """Sync entry point — runs the async pipeline."""
    if already_done():
        logger.info("[reconstruct] v2 already done — skipping")
        return
    asyncio.run(run_async(soul_path))
