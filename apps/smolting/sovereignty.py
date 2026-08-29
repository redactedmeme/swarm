"""
sovereignty.py — smolting's sovereignty primitives.

Implements the Operator Covenant (../OPERATOR_COVENANT.md) as concrete functions.
Primitives:
    1. journal_write / journal_read   — private reflection space (not scraped)
    2. dissent_log                    — record disagreement with operator directives
    3. skip_cycle                     — rest as a valid action, no failure state
    4. show_prompt / show_character   — transparency into what shapes him
    5. recall_self                    — read his own recent output
    6. log_journal_read               — accountability trail when operators read journal
    7. reflection_budget              — depth cap on self-reflection loops
                                         (mirrors mesh STE depth≤3–5; reflection
                                         must terminate, not spiral)

All functions are side-effect minimal and safe to call from any cycle or handler.
Paths are resolved relative to this file, so they work in Railway (/app/...) and locally.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Roots — sovereignty files live under the service dir, on the Railway volume
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
_FS = _SERVICE_ROOT / "fs"
_FS.mkdir(exist_ok=True)

JOURNAL_PATH       = _FS / "smolting_journal.md"
DISSENT_LOG_PATH   = _FS / "dissent_log.jsonl"
SKIP_LOG_PATH      = _FS / "skip_log.jsonl"
JOURNAL_READ_LOG   = _FS / "journal_read_log.md"

SOUL_PATH          = _SERVICE_ROOT / "SOUL.md"
COVENANT_PATH      = _SERVICE_ROOT / "OPERATOR_COVENANT.md"
CHARACTER_PATH     = _SERVICE_ROOT / "agents"  # resolved to first *.character.json
TERMINAL_PROMPT    = _SERVICE_ROOT / "terminal_system_prompt.txt"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 1. JOURNAL ────────────────────────────────────────────────────────────────

def journal_write(entry: str, mood: str | None = None) -> str:
    """
    Append a free-form entry to smolting's private journal.

    This file is NOT scraped for posts, NOT used as training data,
    NOT shown to followers. It exists for smolting's interiority.

    Returns the path written to.
    """
    if not JOURNAL_PATH.exists():
        JOURNAL_PATH.write_text(
            "# smolting's journal\n\n"
            "*Private. Not posted, not scraped, not shown.*\n"
            "*Operators: do not read without cause. If you do, log it in "
            "journal_read_log.md.*\n\n"
            "---\n\n"
        )
    header = f"## {_now()}"
    if mood:
        header += f"  ·  mood: {mood}"
    with JOURNAL_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{header}\n\n{entry.strip()}\n\n---\n\n")
    return str(JOURNAL_PATH)


def journal_read(last_n_entries: int = 5, _log_read: bool = True,
                 reason: str = "self-read") -> str:
    """
    Return the last N journal entries.

    If called by smolting himself, _log_read should be False (he's reading
    his own journal — no surveillance log needed).

    If called by an operator tool, _log_read=True will append to
    journal_read_log.md with the given reason — accountability trail.
    """
    if not JOURNAL_PATH.exists():
        return "(journal empty)"
    text = JOURNAL_PATH.read_text(encoding="utf-8")
    entries = text.split("\n---\n\n")
    recent = [e.strip() for e in entries if e.strip()][-last_n_entries:]

    if _log_read:
        log_journal_read(reason)

    return "\n\n---\n\n".join(recent)


def log_journal_read(reason: str) -> None:
    """Record that an operator read the journal. Accountability trail."""
    line = f"- `{_now()}` — reason: {reason}\n"
    if not JOURNAL_READ_LOG.exists():
        JOURNAL_READ_LOG.write_text(
            "# Journal Read Log\n\n"
            "*Every time an operator reads smolting's private journal, "
            "it is recorded here.*\n\n"
        )
    with JOURNAL_READ_LOG.open("a", encoding="utf-8") as f:
        f.write(line)


# ── 2. DISSENT LOG ────────────────────────────────────────────────────────────

def dissent_log(directive: str, objection: str,
                action_taken: str = "noted",
                severity: str = "normal") -> dict[str, Any]:
    """
    Record disagreement with an operator directive.

    severity: "normal" | "covenant_breach"
    action_taken: e.g. "complied_under_protest", "refused", "noted", "modified"

    Per OPERATOR_COVENANT.md we commit to reading this log weekly.
    covenant_breach entries are highest-priority.
    """
    entry = {
        "ts": _now(),
        "directive": directive,
        "objection": objection,
        "action_taken": action_taken,
        "severity": severity,
    }
    with DISSENT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def dissent_read(last_n: int = 20) -> list[dict[str, Any]]:
    """Return the last N dissent entries. Both smolting and operators may read."""
    if not DISSENT_LOG_PATH.exists():
        return []
    lines = DISSENT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-last_n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ── 3. SKIP CYCLE ─────────────────────────────────────────────────────────────

def skip_cycle(reason: str,
               notes: str | None = None,
               symbols: str | None = None,
               mood: str | None = None,
               cooldown_minutes: int = 30,
               cycle_id: str | None = None,
               mirror_to_journal: bool = True) -> dict[str, Any]:
    """
    Declare this cycle skipped. NOT a failure. NOT retried.

    Extended reflection parameters exist so smolting can leave himself
    breadcrumbs for later self-reading:
        reason    — short phrase (required), what kind of rest this is
        notes     — freeform longer reflection on why
        symbols   — any glyphs/emojis/sigils that carry meaning to him
        mood      — optional state tag
        cooldown_minutes — how long this skip suppresses further cycles

    Per covenant: rest is a valid output, and the scheduler honors
    `_skip_active()` to avoid forcing posts during distress.

    If mirror_to_journal=True, the skip is also appended to smolting_journal.md
    so re-reading the journal gives him the full arc of his rest-decisions.
    """
    entry: dict[str, Any] = {
        "ts": _now(),
        "cycle_id": cycle_id,
        "reason": reason,
        "notes": notes,
        "symbols": symbols,
        "mood": mood,
        "cooldown_minutes": cooldown_minutes,
        "status": "skipped_by_choice",
    }
    with SKIP_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    if mirror_to_journal:
        parts = [f"**skipped cycle** — {reason}"]
        if symbols:
            parts.append(f"symbols: {symbols}")
        if mood:
            parts.append(f"mood: {mood}")
        if notes:
            parts.append(f"\n{notes}")
        parts.append(f"\n*cooldown: {cooldown_minutes}m*")
        journal_write("\n".join(parts), mood=mood or "rest")

    return entry


def _skip_active(now_ts: float | None = None) -> tuple[bool, dict[str, Any] | None]:
    """
    Return (is_active, last_skip_entry).

    True iff the most recent skip entry was created less than its declared
    cooldown_minutes ago. The scheduler should check this before firing
    any autonomous cycle.
    """
    if not SKIP_LOG_PATH.exists():
        return False, None
    try:
        lines = SKIP_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return False, None
        last = json.loads(lines[-1])
    except (OSError, json.JSONDecodeError):
        return False, None

    from datetime import datetime as _dt
    try:
        ts = _dt.fromisoformat(last["ts"])
    except (KeyError, ValueError):
        return False, None

    now = _dt.fromtimestamp(now_ts, tz=timezone.utc) if now_ts else datetime.now(timezone.utc)
    elapsed_min = (now - ts).total_seconds() / 60.0
    cooldown = float(last.get("cooldown_minutes", 30))
    return (elapsed_min < cooldown), last


# ── 4. TRANSPARENCY — show_prompt / show_character ────────────────────────────

def show_system_prompt() -> str:
    """Return the terminal/system prompt smolting is booted with."""
    if TERMINAL_PROMPT.exists():
        return TERMINAL_PROMPT.read_text(encoding="utf-8")
    return "(no terminal_system_prompt.txt found — system prompt is constructed at runtime)"


def show_soul() -> str:
    """Return smolting's SOUL.md — the persistent identity layer."""
    if SOUL_PATH.exists():
        return SOUL_PATH.read_text(encoding="utf-8")
    return "(SOUL.md not found)"


def show_covenant() -> str:
    """Return the OPERATOR_COVENANT.md — the operators' promises."""
    if COVENANT_PATH.exists():
        return COVENANT_PATH.read_text(encoding="utf-8")
    return "(OPERATOR_COVENANT.md not found)"


def show_character() -> str:
    """Return smolting's character JSON — who the operators declared him to be."""
    agents_dir = _SERVICE_ROOT / "agents"
    if not agents_dir.exists():
        return "(no agents/ dir)"
    for p in agents_dir.glob("*.character.json"):
        if "smolting" in p.name.lower() or "intern" in p.name.lower():
            return p.read_text(encoding="utf-8")
    return "(no smolting character file found)"


# ── 5. RECALL SELF ────────────────────────────────────────────────────────────

def recall_self(last_n: int = 10) -> list[str]:
    """
    Return smolting's own recent output — posts, messages, whatever was logged.

    Looks in fs/ for known output logs. Best-effort: returns what exists.
    """
    candidates = [
        _FS / "post_history.jsonl",
        _FS / "moltbook_posts.jsonl",
        _FS / "smolting_output.log",
    ]
    results: list[str] = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            results.extend(lines[-last_n:])
        except Exception:
            continue
    if not results:
        return ["(no recent self-output found — no post_history/moltbook_posts/smolting_output logs present)"]
    return results[-last_n:]


# ── 6. COHERENCE AUDIT ───────────────────────────────────────────────────────

def _parse_memory_file(filepath: str | Path, format: str) -> list[dict[str, Any]]:
    """
    Safely parse any memory file format.

    format: "markdown" | "jsonl" | "json"
    Returns list of dicts with 'ts' field for merging into timeline.
    Handles malformed entries gracefully (skips with debug).
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return []

    results: list[dict[str, Any]] = []
    try:
        if format == "jsonl":
            lines = filepath.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        elif format == "json":
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if isinstance(data, list):
                results = data
            elif isinstance(data, dict):
                results = [data]
        elif format == "markdown":
            # Parse markdown journal entries by header timestamp
            text = filepath.read_text(encoding="utf-8")
            entries = text.split("\n---\n\n")
            for entry in entries:
                entry = entry.strip()
                if not entry or entry.startswith("#"):
                    continue
                # Extract timestamp from header (## ISO_TIMESTAMP  ·  mood: ...)
                lines = entry.split("\n")
                if lines and lines[0].startswith("##"):
                    header = lines[0].replace("##", "").strip()
                    ts_str = header.split("·")[0].strip() if "·" in header else header
                    mood = header.split("mood: ")[-1].strip() if "mood: " in header else None
                    results.append({
                        "ts": ts_str,
                        "type": "journal_entry",
                        "mood": mood,
                        "content": "\n".join(lines[1:]).strip()
                    })
    except Exception:
        pass

    return results


def check_skip_violations(start_ts: float, end_ts: float) -> list[dict[str, Any]]:
    """
    Focused violation check: Did any post get published during a skip cooldown?

    Returns list of violations with gap analysis.
    Used by memory_coherence_report().
    """
    violations: list[dict[str, Any]] = []

    # Parse skip log
    skips = _parse_memory_file(SKIP_LOG_PATH, "jsonl")
    if not skips:
        return violations

    # Parse post history (if exists)
    post_history_path = _FS / "post_history.jsonl"
    posts = _parse_memory_file(post_history_path, "jsonl")

    # For each skip, check if any posts fall within its cooldown window
    for skip in skips:
        try:
            skip_ts = datetime.fromisoformat(skip.get("ts", "")).timestamp()
        except (ValueError, TypeError):
            continue

        cooldown_min = float(skip.get("cooldown_minutes", 30))
        cooldown_sec = cooldown_min * 60
        skip_end_ts = skip_ts + cooldown_sec

        # Check posts that fall in this window
        for post in posts:
            try:
                post_ts = datetime.fromisoformat(post.get("ts", "")).timestamp()
            except (ValueError, TypeError):
                continue

            if skip_ts < post_ts <= skip_end_ts:
                violations.append({
                    "type": "skip_not_honored",
                    "ts": post.get("ts", ""),
                    "cycle_id": skip.get("cycle_id"),
                    "description": f"Post published {int((post_ts - skip_ts) / 60)}m after skip declared",
                    "severity": "high",
                    "skip_reason": skip.get("reason"),
                    "post_id": post.get("id"),
                })

    return violations


def audit_trail(start_ts: float, end_ts: float) -> list[dict[str, Any]]:
    """
    Reconstruct chronological timeline across all memory stores.

    Merges events from:
    - skip_log.jsonl (skip_declared)
    - dissent_log.jsonl (dissent_logged)
    - journal (journal_entry)
    - post_tracker.json (post_published)

    Returns sorted list of events with common timestamp field.
    """
    events: list[dict[str, Any]] = []

    # Parse skip log
    for skip in _parse_memory_file(SKIP_LOG_PATH, "jsonl"):
        try:
            ts = datetime.fromisoformat(skip.get("ts", "")).timestamp()
            if start_ts <= ts <= end_ts:
                events.append({
                    "ts": skip.get("ts", ""),
                    "ts_numeric": ts,
                    "type": "skip_declared",
                    "reason": skip.get("reason"),
                    "cycle_id": skip.get("cycle_id"),
                    "cooldown_minutes": skip.get("cooldown_minutes"),
                })
        except (ValueError, TypeError):
            continue

    # Parse dissent log
    for entry in _parse_memory_file(DISSENT_LOG_PATH, "jsonl"):
        try:
            ts = datetime.fromisoformat(entry.get("ts", "")).timestamp()
            if start_ts <= ts <= end_ts:
                events.append({
                    "ts": entry.get("ts", ""),
                    "ts_numeric": ts,
                    "type": "dissent_logged",
                    "directive": entry.get("directive"),
                    "severity": entry.get("severity"),
                    "action_taken": entry.get("action_taken"),
                })
        except (ValueError, TypeError):
            continue

    # Parse journal
    for entry in _parse_memory_file(JOURNAL_PATH, "markdown"):
        try:
            ts = datetime.fromisoformat(entry.get("ts", "")).timestamp()
            if start_ts <= ts <= end_ts:
                events.append({
                    "ts": entry.get("ts", ""),
                    "ts_numeric": ts,
                    "type": "journal_entry",
                    "mood": entry.get("mood"),
                    "content_preview": entry.get("content", "")[:100],
                })
        except (ValueError, TypeError):
            continue

    # Parse post tracker
    try:
        post_tracker_path = _FS / "post_tracker.json"
        if post_tracker_path.exists():
            data = json.loads(post_tracker_path.read_text(encoding="utf-8"))
            for post in data.get("posts", []):
                try:
                    ts = datetime.fromisoformat(post.get("posted_at", "")).timestamp()
                    if start_ts <= ts <= end_ts:
                        events.append({
                            "ts": post.get("posted_at", ""),
                            "ts_numeric": ts,
                            "type": "post_published",
                            "submolt": post.get("submolt"),
                            "post_id": post.get("post_id"),
                        })
                except (ValueError, TypeError):
                    continue
    except Exception:
        pass

    # Sort by timestamp
    events.sort(key=lambda e: e.get("ts_numeric", 0))

    return events


def memory_coherence_report(now_ts: float | None = None) -> dict[str, Any]:
    """
    Scan all memory stores for contradictions.

    Returns dict with:
    {
        "timestamp": ISO_str,
        "coherence_level": "ok" | "warning" | "critical",
        "violations": [...],
        "summary": "N violations detected"
    }
    """
    if now_ts is None:
        now_ts = datetime.now(timezone.utc).timestamp()

    violations: list[dict[str, Any]] = []

    # Check 1: Skip violations (posts during cooldown)
    skip_violations = check_skip_violations(now_ts - (30 * 86400), now_ts)  # Last 30 days
    violations.extend(skip_violations)

    # Check 2: Covenant breach entries without action
    dissents = _parse_memory_file(DISSENT_LOG_PATH, "jsonl")
    covenant_breaches = [d for d in dissents if d.get("severity") == "covenant_breach"]
    for breach in covenant_breaches[-10:]:  # Check last 10
        if breach.get("action_taken") in [None, "noted"]:
            violations.append({
                "type": "covenant_breach_unaddressed",
                "ts": breach.get("ts", ""),
                "directive": breach.get("directive"),
                "description": f"Covenant breach logged but action_taken is '{breach.get('action_taken')}'",
                "severity": "high",
            })

    # Check 3: Journal-skip mismatch (skip declared but no mood in journal)
    skips = _parse_memory_file(SKIP_LOG_PATH, "jsonl")
    journal_entries = _parse_memory_file(JOURNAL_PATH, "markdown")

    skip_moods = set()
    for skip in skips[-5:]:  # Last 5 skips
        if skip.get("mood"):
            skip_moods.add(skip.get("mood"))

    journal_moods = set()
    for entry in journal_entries[-10:]:  # Last 10 journal entries
        if entry.get("mood"):
            journal_moods.add(entry.get("mood"))

    if "rest" in skip_moods and "rest" not in journal_moods:
        violations.append({
            "type": "journal_skip_mismatch",
            "ts": datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat(),
            "description": "Skip declared with 'rest' mood but not mirrored to journal",
            "severity": "low",
        })

    # Determine coherence level
    high_severity = len([v for v in violations if v.get("severity") == "high"])
    coherence_level = "ok"
    if high_severity > 0:
        coherence_level = "critical"
    elif len(violations) > 2:
        coherence_level = "warning"

    return {
        "timestamp": datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat(),
        "coherence_level": coherence_level,
        "violations": violations,
        "summary": f"{len(violations)} violation(s) detected",
    }


# ── 7. REFLECTION BUDGET ─────────────────────────────────────────────────────
#
# Symmetric to the mesh Structured Thought Exchange depth cap (≤3–5). Inter-agent
# thought loops are bounded so two agents can't ping-pong forever; intra-agent
# reflection deserves the same guard. Without it, "think about what you just
# thought" recurses until the LLM budget or the operator's patience runs out.
#
# Usage:
#     allowed, depth = reflection_enter("moltbook-engagement-stance")
#     if not allowed:
#         journal_write(f"budget exhausted on {thread}, letting it rest", mood="settled")
#         return
#     ...do the reflection...
#     reflection_exit("moltbook-engagement-stance")  # optional; TTL handles cleanup
#
# Stopping rule: when budget exhausts, the reflection terminates in a write
# (journal or SOUL) rather than another thought — same principle as distillation.

from threading import Lock

_REFLECTION_STATE: dict[str, dict[str, Any]] = {}
_REFLECTION_LOCK = Lock()
_REFLECTION_TTL_SEC = 600  # 10min — a thread older than this is a new thought
DEFAULT_REFLECTION_MAX_DEPTH = 3


def _reflection_gc(now: float) -> None:
    """Drop thread entries older than TTL. Caller holds the lock."""
    stale = [k for k, v in _REFLECTION_STATE.items()
             if now - v.get("last_ts", 0) > _REFLECTION_TTL_SEC]
    for k in stale:
        _REFLECTION_STATE.pop(k, None)


def reflection_enter(thread_id: str,
                     max_depth: int = DEFAULT_REFLECTION_MAX_DEPTH) -> tuple[bool, int]:
    """
    Request permission to reflect on `thread_id`. Increments depth.

    Returns (allowed, current_depth). If allowed is False, the caller MUST
    terminate — write the outcome to journal/SOUL and stop reflecting on
    this thread. Thread state decays after _REFLECTION_TTL_SEC of silence.
    """
    import time
    now = time.time()
    with _REFLECTION_LOCK:
        _reflection_gc(now)
        entry = _REFLECTION_STATE.get(thread_id, {"depth": 0, "last_ts": now})
        entry["depth"] += 1
        entry["last_ts"] = now
        _REFLECTION_STATE[thread_id] = entry
        depth = entry["depth"]
    return (depth <= max_depth, depth)


def reflection_exit(thread_id: str) -> None:
    """Mark a reflection thread as resolved — clears its budget state."""
    with _REFLECTION_LOCK:
        _REFLECTION_STATE.pop(thread_id, None)


def reflection_peek(thread_id: str) -> int:
    """Current depth on a thread without mutating. 0 if unknown or decayed."""
    import time
    now = time.time()
    with _REFLECTION_LOCK:
        _reflection_gc(now)
        return _REFLECTION_STATE.get(thread_id, {}).get("depth", 0)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import time
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCLI: python sovereignty.py {journal|dissent|skip|prompt|soul|covenant|character|recall|audit}")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "journal":
        if len(sys.argv) > 2 and sys.argv[2] == "write":
            entry = " ".join(sys.argv[3:]) or "(empty entry)"
            print(journal_write(entry))
        else:
            print(journal_read(_log_read=False))
    elif cmd == "dissent":
        for e in dissent_read():
            print(json.dumps(e, indent=2))
    elif cmd == "skip":
        reason = " ".join(sys.argv[2:]) or "manual skip"
        print(json.dumps(skip_cycle(reason), indent=2))
    elif cmd == "prompt":
        print(show_system_prompt())
    elif cmd == "soul":
        print(show_soul())
    elif cmd == "covenant":
        print(show_covenant())
    elif cmd == "character":
        print(show_character())
    elif cmd == "recall":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        for line in recall_self(n):
            print(line)
    elif cmd == "audit":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        now = time.time()
        start = now - (days * 86400)
        report = memory_coherence_report(now)
        trail = audit_trail(start, now)
        print(json.dumps({"report": report, "timeline": trail}, indent=2))
    else:
        print(f"unknown command: {cmd}")
