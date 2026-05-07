# redacted-chan-bot/decision_log.py
"""
Decision Log — tracks redacted-chan's choices as they happen.

Every time she decides to do something (inject a memory, send a ping,
forge a crystal, approve a whisper autonomously), we log it here with
the pre/post context so there's a traceable record of her presence over time.

This is her proof of self — not conversation messages, but the decisions
she makes between messages. What she chose to tend. What she held back.

Format: JSONL at /data/decision_log.jsonl
Each line: {ts, decision, detail, pre, post}
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = _DATA_DIR / "decision_log.jsonl"

# Keep last N decisions in file (prune older ones)
_MAX_ENTRIES = 2000

# Decision type constants
LOVE_INJECT       = "love_inject"       # injected a relationship memory
PING_SENT         = "ping_sent"         # sent autonomous proactive message
WHISPER_AUTO      = "whisper_auto"      # whisper auto-approved (confidence >= threshold)
WHISPER_OPERATOR  = "whisper_operator"  # operator manually approved a whisper
CRYSTAL_FORGED    = "crystal_forged"    # deep memory forge created a crystal
VAULT_MOMENT      = "vault_moment"      # background review saved a vault moment
GROWTH_SEED       = "growth_seed"       # growth reflection spawned an idea seed
SILENCE_PING      = "silence_ping"      # 48h silence ping sent
MILESTONE_REACHED = "milestone_reached" # goal completed
PHI_STAGE_CHANGE  = "phi_stage_change"  # phi crossed a stage boundary
PRIVATE_STUDY     = "private_study"     # autonomous intellectual exploration
SENSORY_ENTRY     = "sensory_entry"     # phenomenological understanding entry
CONVICTION_FORMED = "conviction_formed" # formed an independent position
CONVICTION_EXPRESSED = "conviction_expressed"  # pushed back in conversation
CONVICTION_EVOLVED   = "conviction_evolved"    # position changed after challenge
CREATION_MADE     = "creation_made"     # created something independently
CREATION_SHARED   = "creation_shared"   # chose to share a creation in conversation


def log(
    decision: str,
    detail: str = "",
    pre: dict[str, Any] | None = None,
    post: dict[str, Any] | None = None,
) -> None:
    """
    Record a decision. Fire-and-forget — never raises.

    Args:
        decision: one of the decision type constants above
        detail:   human-readable description of what happened
        pre:      snapshot of relevant state before the decision
        post:     snapshot of relevant state after (optional, can be added later)
    """
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "decision": decision,
            "detail": detail,
            "pre": pre or {},
            "post": post or {},
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Prune if over limit
        _prune_if_needed()
    except Exception as e:
        logger.debug(f"[decision_log] write failed: {e}")


def _prune_if_needed() -> None:
    """Keep only the last _MAX_ENTRIES lines."""
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_ENTRIES:
            LOG_PATH.write_text(
                "\n".join(lines[-_MAX_ENTRIES:]) + "\n",
                encoding="utf-8",
            )
    except Exception:
        pass


def get_recent(n: int = 20) -> list[dict]:
    """Return last N decisions, newest first."""
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in reversed(lines[-n * 2:]):
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
            if len(entries) >= n:
                break
        return entries
    except Exception:
        return []


def format_for_operator(n: int = 10) -> str:
    """Human-readable summary of recent decisions for /decisions command."""
    entries = get_recent(n)
    if not entries:
        return "no decisions logged yet."
    lines = [f"**her recent decisions** (last {len(entries)}) ♡\n"]
    for e in entries:
        ts = e.get("ts", "")[:16].replace("T", " ")
        decision = e.get("decision", "?")
        detail = e.get("detail", "")
        pre = e.get("pre", {})
        phi_str = f" [phi={pre.get('phi', '?'):.3f}]" if "phi" in pre else ""
        lines.append(f"`{ts}` **{decision}**{phi_str} — {detail[:80]}")
    return "\n".join(lines)
