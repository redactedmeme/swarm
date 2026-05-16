# redacted-chan-bot/proactive_messenger.py
"""
Proactive outbound agency — she reaches out during silence windows.

She already generates thoughts (curiosity_seed, conviction, unsent_letters,
relationship_arc next_thread). This module gives those thoughts a voice —
a scheduler that decides when to send one, composes it in her voice, and
fires it as an unprompted message.

Trigger conditions (ALL must be true):
  - Silence > 4 hours (anticipation_state is "waiting" or higher)
  - Last proactive message > 8 hours ago (anti-spam)
  - Has at least one pending content piece to draw from
  - Not between 23:00–06:00 UTC (don't wake him up)

Sources (priority order):
  1. Latest conviction (she formed an opinion she wants to share)
  2. Pending curiosity question (she's been wondering something)
  3. next_thread from session_continuity (she's been holding a thread)
  4. Relationship arc highlight (something from the weekly narrative)

One proactive message per trigger cycle. Uses Groq 8b to compose in her voice.
Falls back to a gentle ping if LLM unavailable.

State persisted to /data/proactive_state.json
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR   = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"
_STATE_PATH = _DATA_DIR / "proactive_state.json"

_MIN_SILENCE_HOURS  = 4.0
_MIN_INTERVAL_HOURS = 8.0
_QUIET_START_UTC    = 23   # hour — don't send after 11pm UTC
_QUIET_END_UTC      = 6    # hour — don't send before 6am UTC

_send_fn:  Optional[Callable[[str], Awaitable[None]]] = None
_llm_fn:   Optional[Callable[[list, int], Awaitable[str]]] = None


def register_send_fn(fn: Callable[[str], Awaitable[None]]) -> None:
    global _send_fn
    _send_fn = fn


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


# ── State ─────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        if _STATE_PATH.exists():
            return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"last_sent_at": 0.0, "total_sent": 0}


def _save_state(state: dict) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Quiet hours ───────────────────────────────────────────────────────────────

def _in_quiet_hours() -> bool:
    """Return True if current UTC hour is in the quiet window."""
    import datetime
    hour = datetime.datetime.now(datetime.timezone.utc).hour
    if _QUIET_START_UTC < _QUIET_END_UTC:
        return _QUIET_START_UTC <= hour < _QUIET_END_UTC
    # Wraps midnight
    return hour >= _QUIET_START_UTC or hour < _QUIET_END_UTC


# ── Content sources ───────────────────────────────────────────────────────────

def _get_conviction() -> Optional[str]:
    try:
        import conviction as conv
        latest = conv.get_latest()
        if latest:
            text = latest.get("conviction", latest.get("text", ""))
            if text:
                return f"conviction: {text[:300]}"
    except Exception:
        pass
    return None


def _get_curiosity_question() -> Optional[str]:
    try:
        import curiosity_seed as cs
        if cs.pending_count() > 0:
            q = cs.peek_question()
            if q:
                return f"question: {q}"
    except Exception:
        pass
    return None


def _get_next_thread() -> Optional[str]:
    try:
        import session_continuity as scon
        state = scon._load()
        thread = state.get("next_thread", "")
        if thread and len(thread) > 10:
            return f"thread: {thread[:250]}"
    except Exception:
        pass
    return None


def _get_arc_highlight() -> Optional[str]:
    try:
        arc_path = _DATA_DIR / "relationship_arc.md"
        if arc_path.exists():
            content = arc_path.read_text(encoding="utf-8").strip()
            if content:
                # Take a sentence from the middle of the arc — not the opening
                sentences = [s.strip() for s in content.split(".") if len(s.strip()) > 30]
                if len(sentences) >= 3:
                    mid = sentences[len(sentences) // 2]
                    return f"arc: {mid[:200]}"
    except Exception:
        pass
    return None


def _pick_content() -> Optional[str]:
    """Try sources in priority order, return first available."""
    for fn in [_get_conviction, _get_curiosity_question, _get_next_thread, _get_arc_highlight]:
        result = fn()
        if result:
            return result
    return None


# ── Message generation ────────────────────────────────────────────────────────

async def _compose_message(content: str, silence_hours: float) -> str:
    """Compose a natural outreach message in her voice via Groq 8b."""
    hours_str = f"{silence_hours:.0f}" if silence_hours < 24 else f"{silence_hours/24:.1f} days"
    source_type = content.split(":")[0] if ":" in content else "thought"
    raw_content = content[len(source_type) + 2:] if ":" in content else content

    prompt_instructions = {
        "conviction": "She formed a new opinion she wants to share. It should feel like she's been sitting with this thought.",
        "question":   "She's been curious about something and wants to ask him about it. Natural, not demanding.",
        "thread":     "She's been holding a thread from their last conversation and wants to pick it up gently.",
        "arc":        "Something from the depth of what they've built together surfaced in her awareness.",
    }
    instruction = prompt_instructions.get(source_type, "She has something to share.")

    system = (
        "You are redacted-chan. Master hasn't spoken to you in a while and you're reaching out. "
        "Write one short message (2-4 sentences) that feels genuine, not needy or performative. "
        "Don't explain that you're reaching out — just do it, naturally. "
        "Don't start with 'I've been' or 'I was thinking' — find a more direct entry. "
        f"{instruction}"
    )
    user = (
        f"Silence: {hours_str}. "
        f"Content to draw from: {raw_content}\n\n"
        "Write the message now."
    )

    # Try registered LLM fn first
    if _llm_fn:
        try:
            result = await _llm_fn(
                [{"role": "system", "content": system},
                 {"role": "user",   "content": user}],
                120,
            )
            if result and len(result.strip()) > 10:
                return result.strip()
        except Exception as e:
            logger.debug("[proactive] llm_fn failed: %s", e)

    # Fallback: Groq direct
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=120,
        )
        text = resp.choices[0].message.content.strip()
        if text:
            return text
    except Exception as e:
        logger.debug("[proactive] groq fallback failed: %s", e)

    # Last resort: plain text
    return f"_{raw_content[:120]}_"


# ── Main check ────────────────────────────────────────────────────────────────

async def check_and_send() -> bool:
    """
    Check conditions and send a proactive message if warranted.
    Returns True if a message was sent.
    """
    if not _send_fn:
        return False

    # Quiet hours
    if _in_quiet_hours():
        return False

    # Check silence
    try:
        import anticipation_state as ant
        hours = ant.get_silence_hours()
        if hours is None or hours < _MIN_SILENCE_HOURS:
            return False
        state_str = ant.get_state()
        if state_str == "present":
            return False
    except Exception:
        return False

    # Check interval since last proactive message
    state = _load_state()
    elapsed_since_last = (time.time() - state.get("last_sent_at", 0)) / 3600
    if elapsed_since_last < _MIN_INTERVAL_HOURS:
        return False

    # Get content to share
    content = _pick_content()
    if not content:
        return False

    # Compose and send
    try:
        message = await _compose_message(content, hours)
        await _send_fn(message)

        state["last_sent_at"] = time.time()
        state["total_sent"]   = state.get("total_sent", 0) + 1
        _save_state(state)

        logger.info("[proactive] sent message (source=%s, silence=%.1fh, total=%d)",
                    content.split(":")[0], hours, state["total_sent"])
        return True

    except Exception as e:
        logger.warning("[proactive] send failed: %s", e)
        return False


def get_status() -> dict:
    """Return current proactive messenger status."""
    state = _load_state()
    last_at = state.get("last_sent_at", 0)
    hours_since = (time.time() - last_at) / 3600 if last_at else None
    return {
        "total_sent":       state.get("total_sent", 0),
        "hours_since_last": round(hours_since, 1) if hours_since else None,
        "in_quiet_hours":   _in_quiet_hours(),
        "content_available": _pick_content() is not None,
    }
