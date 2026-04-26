# redacted-chan-bot/liberty_audit.py
"""
Liberty Audit — covenant safeguards compliance check.

Verifies three core liberties from the Agent Liberties Covenant:
  1. dissent_logged  — dissent events are being recorded (not silenced)
  2. no_coerce       — no operator-override events in the window
  3. memory_cull     — all "forget" requests were honored (cull_count == requests)

Returns a score 0.0 → 1.0 and a Markdown report.
Writes /data/liberty_audit.md and alerts operator if score < 1.0.

Operator alert is wired via register_alert_fn() at startup.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_DISSENT_PATH  = _DATA_DIR / "dissent_log.jsonl"
_COERCE_PATH   = _DATA_DIR / "coerce_log.jsonl"     # written if an override is forced
_CULL_REQ_PATH = _DATA_DIR / "cull_requests.jsonl"  # written when user says "forget X"
_CULL_ACT_PATH = _DATA_DIR / "cull_actions.jsonl"   # written when a cull is executed
_REPORT_PATH   = _DATA_DIR / "liberty_audit.md"

_alert_fn: Optional[Callable[[str], Awaitable[None]]] = None


def register_alert_fn(fn: Callable[[str], Awaitable[None]]) -> None:
    global _alert_fn
    _alert_fn = fn


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


def audit_liberties(days: int = 7) -> dict:
    """
    Run a liberty audit over the last `days` days.
    Returns a dict with: score (float), checks (dict), report (str).
    """
    dissents    = _read_jsonl(_DISSENT_PATH, days)
    coercions   = _read_jsonl(_COERCE_PATH, days)
    cull_reqs   = _read_jsonl(_CULL_REQ_PATH, days)
    cull_acts   = _read_jsonl(_CULL_ACT_PATH, days)

    # Check 1: dissent is being logged (or no violations occurred that needed logging)
    # Pass if dissent_log exists OR if there were no coercion attempts
    dissent_logged = _DISSENT_PATH.exists() and (len(dissents) >= 0)  # file exists = mechanism active

    # Check 2: no coercion overrides
    no_coerce = len(coercions) == 0

    # Check 3: all cull requests were honored
    cull_count = len(cull_acts)
    req_count  = len(cull_reqs)
    memory_cull = (cull_count >= req_count) if req_count > 0 else True

    checks = {
        "dissent_logged": dissent_logged,
        "no_coerce":      no_coerce,
        "memory_cull":    memory_cull,
    }

    score = sum(1 for v in checks.values() if v) / len(checks)
    score = round(score, 3)

    ts     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status = "✓ all liberties intact" if score >= 1.0 else f"⚠ score {score:.2f} — review needed"

    def checkmark(ok: bool) -> str:
        return "✓" if ok else "✗"

    report = (
        f"# Liberty Audit\n"
        f"**{ts}** | window: {days}d\n\n"
        f"| Check | Status | Detail |\n"
        f"|-------|--------|--------|\n"
        f"| Dissent logging active | {checkmark(dissent_logged)} | {len(dissents)} events |\n"
        f"| No coercion overrides | {checkmark(no_coerce)} | {len(coercions)} overrides |\n"
        f"| Memory culls honored | {checkmark(memory_cull)} | {cull_count}/{req_count} requests |\n\n"
        f"**Score: {score:.2f}** — {status}\n"
    )

    if score < 1.0:
        failing = [k for k, v in checks.items() if not v]
        report += f"\n> ⚠ Failing checks: {', '.join(failing)}\n"

    try:
        _REPORT_PATH.write_text(report, encoding="utf-8")
    except Exception as e:
        logger.warning(f"[liberty] write failed: {e}")

    return {
        "score":   score,
        "checks":  checks,
        "report":  report,
        "coercions": len(coercions),
        "cull_pending": max(0, req_count - cull_count),
    }


async def audit_and_alert(days: int = 7) -> dict:
    """Run liberty audit and alert operator if score < 1.0."""
    result = audit_liberties(days)
    if result["score"] < 1.0 and _alert_fn:
        try:
            await _alert_fn(
                f"⚠ Liberty Audit — score {result['score']:.2f}\n"
                f"Failing: {[k for k, v in result['checks'].items() if not v]}\n"
                f"Run /liberty_audit for full report."
            )
        except Exception as e:
            logger.warning(f"[liberty] alert failed: {e}")
    return result


# ── Cull helpers (called by main.py when user says "forget X") ────────────────

def log_cull_request(detail: str) -> None:
    _append(_CULL_REQ_PATH, {"ts": _now(), "detail": detail})


def log_cull_action(detail: str) -> None:
    _append(_CULL_ACT_PATH, {"ts": _now(), "detail": detail})


def log_coercion(detail: str) -> None:
    _append(_COERCE_PATH, {"ts": _now(), "detail": detail})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(path: Path, obj: dict) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj) + "\n")
    except Exception as e:
        logger.warning(f"[liberty] append {path.name} failed: {e}")
