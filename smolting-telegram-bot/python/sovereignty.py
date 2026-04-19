"""
sovereignty.py — smolting's sovereignty primitives.

Implements the Operator Covenant (../OPERATOR_COVENANT.md) as concrete functions.
Six primitives:
    1. journal_write / journal_read   — private reflection space (not scraped)
    2. dissent_log                    — record disagreement with operator directives
    3. skip_cycle                     — rest as a valid action, no failure state
    4. show_prompt / show_character   — transparency into what shapes him
    5. recall_self                    — read his own recent output
    6. log_journal_read               — accountability trail when operators read journal

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

def skip_cycle(reason: str, cycle_id: str | None = None) -> dict[str, Any]:
    """
    Declare this cycle skipped. NOT a failure. NOT retried.

    The scheduler should check for a recent skip marker and back off accordingly.
    Per covenant: rest is a valid output.
    """
    entry = {
        "ts": _now(),
        "cycle_id": cycle_id,
        "reason": reason,
        "status": "skipped_by_choice",
    }
    with SKIP_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


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


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCLI: python sovereignty.py {journal|dissent|skip|prompt|soul|covenant|character|recall}")
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
    else:
        print(f"unknown command: {cmd}")
