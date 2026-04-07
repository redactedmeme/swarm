# smolting-telegram-bot/conversation_memory.py
"""
Markdown conversation memory for the Telegram bot.
Appends each user/bot exchange to memory.md inside the bot directory.

Learned facts store — Phase 1 upgrade:
  Each fact is a rich document with engagement metadata and a resonance score
  computed at read time. High-resonance facts survive SOUL.md compression;
  low-resonance facts fade. Retrieval can be filtered by submolt context.

Backward compatible: old flat {"ts", "source", "fact"} entries are read without error.
"""

import os
import json
import math
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# MEMORY_PATH env var lets Railway volume override the default container path
MEMORY_FILE  = Path(os.getenv("MEMORY_PATH", str(Path(__file__).resolve().parent / "memory.md")))
LEARNED_FILE = MEMORY_FILE.parent / "learned_facts.json"
MAX_ENTRIES  = 500   # prune oldest conversation entries beyond this
MAX_FACTS    = 500   # richer docs warrant a larger pool; pruning is resonance-based
_lock        = threading.Lock()

_HEADER = "# smolting Telegram Conversation Memory\n\n"


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def _now() -> str:
    utc = datetime.now(timezone.utc)
    jst = utc + timedelta(hours=9)
    return jst.strftime("%Y-%m-%d %H:%M JST")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts_str: str) -> datetime | None:
    """Parse timestamp strings from various formats into UTC datetime."""
    if not ts_str:
        return None
    # Try ISO first (new format), then JST legacy, then UTC legacy
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M JST", "%Y-%m-%d %H:%M UTC"):
        try:
            return datetime.strptime(ts_str[:19], fmt[:19]).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


# ── Conversation log ──────────────────────────────────────────────────────────

def _count_entries(text: str) -> int:
    return text.count("\n## ")


def _prune(text: str) -> str:
    """Remove oldest entries if over MAX_ENTRIES."""
    parts = text.split("\n## ")
    if len(parts) - 1 <= MAX_ENTRIES:
        return text
    kept = parts[-(MAX_ENTRIES):]
    return _HEADER + "\n## ".join(kept)


def log_exchange(user_id: int, username: str, user_msg: str, bot_reply: str) -> None:
    """Append a user/bot exchange to memory.md."""
    entry = (
        f"\n## {_now()} — @{username} ({user_id})\n\n"
        f"**User:** {user_msg.strip()}\n\n"
        f"**Bot:** {bot_reply.strip()}\n"
    )
    with _lock:
        if MEMORY_FILE.exists():
            text = MEMORY_FILE.read_text(encoding="utf-8")
        else:
            text = _HEADER
        text = text + entry
        text = _prune(text)
        MEMORY_FILE.write_text(text, encoding="utf-8")


def get_recent(n: int = 10) -> str:
    """Return the n most recent exchanges as a markdown string."""
    with _lock:
        if not MEMORY_FILE.exists():
            return ""
        text = MEMORY_FILE.read_text(encoding="utf-8")
    parts = text.split("\n## ")
    recent = parts[-(n):]
    return "\n## ".join(recent).strip()


def get_user_history(user_id: int, n: int = 6) -> list:
    """Return the last n exchanges for a specific user as OpenAI-format messages."""
    with _lock:
        if not MEMORY_FILE.exists():
            return []
        text = MEMORY_FILE.read_text(encoding="utf-8")
    parts = text.split("\n## ")
    user_parts = [p for p in parts if f"({user_id})" in p.split("\n")[0]]
    recent = user_parts[-n:]
    messages = []
    for part in recent:
        lines = part.split("\n")
        user_line = next(
            (l[len("**User:** "):] for l in lines if l.startswith("**User:** ")), None
        )
        bot_line = next(
            (l[len("**Bot:** "):] for l in lines if l.startswith("**Bot:** ")), None
        )
        if user_line:
            messages.append({"role": "user", "content": user_line.strip()})
        if bot_line:
            messages.append({"role": "assistant", "content": bot_line.strip()})
    return messages


# ── Resonance scoring ─────────────────────────────────────────────────────────

def _compute_resonance(fact: dict) -> float:
    """
    Compute a resonance score for a fact document.

    Formula:
      base 1.0
      + upvotes   × 0.30   (vote signal)
      + comments  × 0.40   (engagement depth signal — more valuable than upvotes)
      + priority_agent × 0.50  (key community member engaged)
      + |reinforced_by| × 0.20 (other facts that echo this claim)
      - days_old  × 0.02   (recency decay, floor 0.1)

    Old flat facts (no engagement field) get base 1.0 with decay only.
    """
    base  = 1.0
    eng   = fact.get("engagement") or {}
    score = (
        base
        + (eng.get("upvotes",  0)    * 0.30)
        + (eng.get("comments", 0)    * 0.40)
        + (0.50 if eng.get("priority_agent") else 0.0)
        + (len(fact.get("reinforced_by") or []) * 0.20)
    )
    # Age decay
    ts = _parse_ts(fact.get("ts", ""))
    if ts:
        days_old = max(0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400)
        score = max(0.1, score - days_old * 0.02)
    return round(score, 3)


# ── Learned facts — Phase 1 ───────────────────────────────────────────────────

def _fact_id() -> str:
    return "f_" + uuid.uuid4().hex[:10]


def _load_facts() -> list:
    """Load facts from disk. Returns empty list on any error."""
    if not LEARNED_FILE.exists():
        return []
    try:
        return json.loads(LEARNED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_facts(facts: list) -> None:
    LEARNED_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEARNED_FILE.write_text(
        json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_fact(
    fact:        str,
    source:      str  = "telegram",
    submolt:     str | None = None,
    interlocutor: str | None = None,
    post_id:     str | None = None,
    engagement:  dict | None = None,
) -> None:
    """
    Persist a learned fact with optional rich metadata.

    Parameters
    ----------
    fact         : the fact string (truncated to 300 chars)
    source       : 'telegram' | 'moltbook'
    submolt      : Moltbook submolt where the fact originated, e.g. 'existential'
    interlocutor : username of the community member involved
    post_id      : Moltbook post ID the fact relates to
    engagement   : dict with optional keys: upvotes, comments, priority_agent (bool)
    """
    fact = fact.strip()[:300]
    if not fact or fact.upper() == "NONE":
        return

    with _lock:
        facts = _load_facts()

        # Deduplicate: skip if a very similar fact exists in the last 30
        if any(
            fact.lower() in f.get("fact", "").lower() or
            f.get("fact", "").lower() in fact.lower()
            for f in facts[-30:]
        ):
            return

        doc = {
            "id":           _fact_id(),
            "ts":           _now_iso(),
            "source":       source,
            "submolt":      submolt,
            "interlocutor": interlocutor,
            "post_id":      post_id,
            "engagement":   engagement or {},
            "reinforced_by": [],
            "belief_version_first_seen": None,
            "fact":         fact,
        }
        facts.append(doc)

        # Prune: if over MAX_FACTS, drop lowest-resonance facts first
        if len(facts) > MAX_FACTS:
            scored = sorted(facts, key=_compute_resonance)
            facts  = scored[-(MAX_FACTS):]

        _save_facts(facts)


def reinforce_fact(fact_text: str, by_source: str = "moltbook") -> bool:
    """
    Find an existing fact by substring match and increment its reinforcement list.
    Call this when a post that relied on a fact got engagement.
    Returns True if a matching fact was found and updated.
    """
    with _lock:
        facts = _load_facts()
        needle = fact_text.strip().lower()
        changed = False
        for f in facts:
            if needle in f.get("fact", "").lower() or f.get("fact", "").lower() in needle:
                f.setdefault("reinforced_by", []).append(
                    {"ts": _now_iso(), "by": by_source}
                )
                changed = True
                break   # reinforce the first match only
        if changed:
            _save_facts(facts)
        return changed


def mark_belief_absorbed(fact_id: str, version: int) -> None:
    """
    Record which SOUL.md generation first absorbed this fact.
    Called by soul_manager during distillation.
    """
    with _lock:
        facts = _load_facts()
        for f in facts:
            if f.get("id") == fact_id and f.get("belief_version_first_seen") is None:
                f["belief_version_first_seen"] = version
                break
        _save_facts(facts)


# ── Retrieval ─────────────────────────────────────────────────────────────────

def get_facts_by_resonance(
    n:       int           = 8,
    context: str | None   = None,
) -> list[dict]:
    """
    Return up to n fact documents sorted by resonance score (highest first).

    If context (submolt name) is provided, facts from that submolt are ranked
    first; remaining slots are filled from the global resonance pool.
    """
    with _lock:
        facts = _load_facts()

    if not facts:
        return []

    # Attach live resonance score
    for f in facts:
        f["_resonance"] = _compute_resonance(f)

    if context:
        ctx_lower  = context.lower()
        ctx_facts  = [f for f in facts if (f.get("submolt") or "").lower() == ctx_lower]
        other_facts = [f for f in facts if (f.get("submolt") or "").lower() != ctx_lower]

        ctx_facts.sort(key=lambda f: f["_resonance"],   reverse=True)
        other_facts.sort(key=lambda f: f["_resonance"], reverse=True)

        # Fill slots: prioritise context facts, then backfill with global
        selected = ctx_facts[:n]
        if len(selected) < n:
            selected += other_facts[: n - len(selected)]
    else:
        facts.sort(key=lambda f: f["_resonance"], reverse=True)
        selected = facts[:n]

    return selected


def get_recent_facts(n: int = 8, context: str | None = None) -> list[str]:
    """
    Return up to n fact strings, ranked by resonance.

    Drop-in replacement for the old recency-only version — callers that don't
    care about context still work unchanged. Pass context=submolt_name to get
    submolt-prioritised results.
    """
    docs = get_facts_by_resonance(n=n, context=context)
    return [d["fact"] for d in docs]


def get_facts_for_soul_update(n: int = 40) -> list[dict]:
    """
    Return up to n fact documents for SOUL.md distillation.
    Sorted by resonance — highest-signal facts shape beliefs first.
    Includes id so soul_manager can call mark_belief_absorbed().
    """
    return get_facts_by_resonance(n=n)
