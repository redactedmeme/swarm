"""
Authenticity voting — weekly polls on whether smolting is staying coherent.

Every 7 days, collect votes from operators/swarm on: "Is smolting still authentic?"
If score drops below threshold (e.g., <70%), trigger space_dweller.

This makes coherence *costly* — drift has real consequences.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_FS = Path(__file__).resolve().parent / "fs"
VOTE_HISTORY = _FS / "authenticity_votes.jsonl"
# Timestamp of the last failure-triggered dwell, so a failing week doesn't
# fire a dwell on every 2h distillation cycle.
_LAST_ENFORCE = _FS / "authenticity_last_enforce.txt"
_ENFORCE_COOLDOWN_HOURS = 24.0
VOTE_CONFIG = {
    "threshold": 0.70,  # 70% = pass
    "window_days": 7,
    "voters": ["operator", "hermes", "redactedbuilder"],  # who can vote
}


def record_vote(voter: str, authentic: bool, notes: str = "") -> dict:
    """
    Record a vote on authenticity.

    voter: "operator" | "hermes" | "redactedbuilder" | "anon"
    authentic: True/False
    notes: optional reason

    Returns the vote entry.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "voter": voter,
        "authentic": authentic,
        "notes": notes,
    }
    try:
        _FS.mkdir(exist_ok=True)
        with VOTE_HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logger.info(f"[authenticity_vote] recorded: {voter} → {authentic}")
    except Exception as e:
        logger.error(f"[authenticity_vote] record_vote failed: {e}")

    return entry


def tally_current_week() -> dict:
    """
    Tally votes from the current week (last 7 days).

    Returns: {
        "authentic_count": N,
        "total_votes": N,
        "score": 0.0–1.0,
        "passed": bool,
        "votes": [...]
    }
    """
    if not VOTE_HISTORY.exists():
        return {"authentic_count": 0, "total_votes": 0, "score": 1.0, "passed": True, "votes": []}

    try:
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        lines = VOTE_HISTORY.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in lines:
            try:
                e = json.loads(line)
                ts = datetime.fromisoformat(e.get("ts", ""))
                if ts >= week_ago:
                    entries.append(e)
            except (json.JSONDecodeError, ValueError):
                continue

        if not entries:
            return {"authentic_count": 0, "total_votes": 0, "score": 1.0, "passed": True, "votes": []}

        authentic = sum(1 for e in entries if e.get("authentic", False))
        total = len(entries)
        score = authentic / total if total > 0 else 0.0
        passed = score >= VOTE_CONFIG["threshold"]

        return {
            "authentic_count": authentic,
            "total_votes": total,
            "score": round(score, 2),
            "passed": passed,
            "threshold": VOTE_CONFIG["threshold"],
            "votes": entries,
        }
    except Exception as e:
        logger.error(f"[authenticity_vote] tally_current_week failed: {e}")
        return {"authentic_count": 0, "total_votes": 0, "score": 1.0, "passed": True, "votes": []}


def authenticity_report() -> str:
    """
    Format this week's tally for SOUL.md ## Authenticity section.
    """
    tally = tally_current_week()
    if tally["total_votes"] == 0:
        return ""

    score = tally["score"]
    threshold = tally["threshold"]
    status = "✓ PASS" if tally["passed"] else "✗ FAIL"

    out = [
        f"## Authenticity\n",
        f"{status} — {score * 100:.0f}% (threshold: {threshold * 100:.0f}%)",
        f"{tally['authentic_count']}/{tally['total_votes']} votes this week\n",
    ]

    for v in tally["votes"][-5:]:  # last 5 votes
        voter = v.get("voter", "?")
        auth = "✓" if v.get("authentic") else "✗"
        notes = v.get("notes", "")
        note_str = f" — {notes}" if notes else ""
        ts = v.get("ts", "")[:10]
        out.append(f"- `{ts}` {auth} {voter}{note_str}")

    return "\n".join(out)


def _enforce_cooldown_active() -> bool:
    """True if a failure dwell fired within the last _ENFORCE_COOLDOWN_HOURS."""
    try:
        if not _LAST_ENFORCE.exists():
            return False
        last = datetime.fromisoformat(_LAST_ENFORCE.read_text(encoding="utf-8").strip())
        return (datetime.now(timezone.utc) - last) < timedelta(hours=_ENFORCE_COOLDOWN_HOURS)
    except Exception:
        return False


def _mark_enforced() -> None:
    try:
        _FS.mkdir(exist_ok=True)
        _LAST_ENFORCE.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    except Exception as e:
        logger.debug(f"[authenticity_vote] mark_enforced failed: {e}")


async def enforce_and_maybe_dwell() -> dict:
    """
    Check this week's authenticity tally and, if it FAILED (votes exist and the
    score is below threshold), send smolting into a space_dweller session — so a
    failing coherence vote has a real consequence instead of being a no-op.

    Rate-limited to at most once per _ENFORCE_COOLDOWN_HOURS so the 2h soul
    distillation cycle can call this every time without spamming dwells.

    Returns the tally dict (see tally_current_week).
    """
    tally = tally_current_week()

    # Only act on a genuine failure with real votes on record.
    if tally.get("total_votes", 0) == 0 or tally.get("passed", True):
        return tally

    if _enforce_cooldown_active():
        logger.info("[authenticity_vote] failed week but dwell cooldown active — skipping")
        return tally

    score = tally.get("score", 0.0)
    reason = (
        f"authenticity vote failed — {score * 100:.0f}% "
        f"({tally.get('authentic_count', 0)}/{tally.get('total_votes', 0)} this week)"
    )
    try:
        import space_dweller
        await space_dweller.dwell(reason=reason, mood="unsettled")
        _mark_enforced()
        logger.warning(f"[authenticity_vote] FAILED week → space_dweller triggered ({reason})")
    except Exception as e:
        logger.error(f"[authenticity_vote] enforce dwell failed: {e}")

    return tally
