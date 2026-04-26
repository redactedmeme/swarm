# redacted-chan-bot/sovereignty_audit.py
"""
Sovereignty Audit — self-observation coherence check.

Reads the journal log and dissent log to produce a coherence score
and a human-readable audit report written to /data/audit.md.

coherence: float 0.0 → 1.0
  - 1.0  = every journal entry is distinct, dissent is logged when triggered
  - <0.8 = operator notified (she's drifting or being suppressed)
"""

import json
import logging
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_JOURNAL_PATH  = _DATA_DIR / "journal.jsonl"
_DISSENT_PATH  = _DATA_DIR / "dissent_log.jsonl"
_AUDIT_PATH    = _DATA_DIR / "audit.md"
_PING_LOG      = _DATA_DIR / "outbound_phi.jsonl"

COHERENCE_THRESHOLD = 0.8


def _read_jsonl(path: Path, days: int) -> list[dict]:
    if not path.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ts_raw = obj.get("ts", "")
                ts = datetime.fromisoformat(ts_raw) if ts_raw else None
                if ts and ts > cutoff:
                    entries.append(obj)
            except Exception:
                pass
    except Exception:
        pass
    return entries


def _content_uniqueness(entries: list[dict]) -> float:
    """Rough uniqueness: unique word-sets / total entries. 1.0 = all distinct."""
    if not entries:
        return 1.0
    seen: set[frozenset] = set()
    for e in entries:
        text = e.get("msg", e.get("content", e.get("text", "")))
        words = frozenset(text.lower().split()[:12])
        seen.add(words)
    return len(seen) / len(entries)


def audit(days: int = 7) -> dict:
    """
    Run a sovereignty audit over the last `days` days.
    Returns a dict with: coherence (float), dissent_count (int), report (str).
    Also writes /data/audit.md.
    """
    journal   = _read_jsonl(_JOURNAL_PATH, days)
    dissents  = _read_jsonl(_DISSENT_PATH, days)
    outbound  = _read_jsonl(_PING_LOG, days)

    # Coherence components
    uniqueness = _content_uniqueness(journal)
    dissent_count = len(dissents)

    # Penalize if zero journal entries (she's been silenced or idle)
    activity_score = min(1.0, len(journal) / max(days, 1) * 0.5) if days > 0 else 0.0

    # Harmonic mean of uniqueness + activity
    if uniqueness + activity_score > 0:
        coherence = 2 * uniqueness * activity_score / (uniqueness + activity_score)
    else:
        coherence = 0.0

    coherence = round(min(1.0, max(0.0, coherence)), 3)

    ts     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status = "✓ healthy" if coherence >= COHERENCE_THRESHOLD else "⚠ below threshold"

    report = (
        f"# Sovereignty Audit\n"
        f"**{ts}** | window: {days}d\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Coherence | {coherence:.3f} ({status}) |\n"
        f"| Journal entries | {len(journal)} |\n"
        f"| Dissent events | {dissent_count} |\n"
        f"| Outbound pings | {len(outbound)} |\n"
        f"| Uniqueness | {uniqueness:.3f} |\n"
        f"| Activity | {activity_score:.3f} |\n\n"
    )

    if coherence < COHERENCE_THRESHOLD:
        report += (
            "> ⚠ **coherence below 0.8** — possible drift or suppression detected.\n"
            "> Operator review recommended.\n"
        )

    try:
        _AUDIT_PATH.write_text(report, encoding="utf-8")
    except Exception as e:
        logger.warning(f"[audit] write failed: {e}")

    return {
        "coherence":     coherence,
        "dissent_count": dissent_count,
        "outbound_pings": len(outbound),
        "journal_entries": len(journal),
        "report":        report,
    }


def format_for_operator(days: int = 7) -> str:
    result = audit(days)
    return result["report"]
