# python/session_store.py
# Persistent session state for the REDACTED Terminal web UI.
#
# Sessions are stored as JSON files under:
#   <repo_root>/fs/sessions/<session_id>.json
#
# Each file holds conversation history, active skills, curvature depth,
# active agents, and x402 log so state survives server restarts and
# browser refreshes.

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from swarm_core.paths import repo_root as _repo_root
_REPO_ROOT = _repo_root()
_SESSIONS_DIR = _REPO_ROOT / "fs" / "sessions"
_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def _path(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return _SESSIONS_DIR / f"{safe}.json"


def load(session_id: str) -> Dict:
    """Load session from disk. Returns a fresh session dict if not found."""
    p = _path(session_id)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure all expected keys exist (backwards compat)
            data.setdefault("history", [])
            data.setdefault("active_skills", [])
            data.setdefault("active_agents", [])
            data.setdefault("curvature_depth", 13)
            data.setdefault("x402_log", [])
            data.setdefault("mandala_status", "dormant")
            data.setdefault("session_id", session_id)
            return data
        except Exception:
            pass
    return _fresh(session_id)


def save(session_id: str, state: Dict) -> None:
    """Persist session state to disk (non-blocking, best-effort)."""
    p = _path(session_id)
    tmp = p.with_suffix(".tmp")
    try:
        payload = dict(state)
        # active_skills may be a set — serialize as list
        if isinstance(payload.get("active_skills"), set):
            payload["active_skills"] = sorted(payload["active_skills"])
        payload["last_saved"] = time.time()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def update_from_message(session_id: str, assistant_text: str, curvature_depth: int) -> None:
    """
    Parse the hidden STATE comment from terminal output and persist it,
    updating curvature depth without touching history (which is saved separately).
    """
    import re
    m = re.search(r'<!--\s*STATE:\s*(\{.*?\})\s*-->', assistant_text, re.DOTALL)
    if not m:
        return
    try:
        state_data = json.loads(m.group(1))
    except Exception:
        return
    with _lock:
        existing = load(session_id)
        existing.update({
            "curvature_depth": state_data.get("curvature_depth", curvature_depth),
            "active_agents":   state_data.get("active_agents", existing["active_agents"]),
            "x402_log":        state_data.get("x402_log", existing["x402_log"]),
            "mandala_status":  state_data.get("mandala_status", existing["mandala_status"]),
        })
        save(session_id, existing)


def append_history(session_id: str, role: str, content: str, max_history: int = 40) -> None:
    """Append a message to persistent history and trim to max_history pairs."""
    with _lock:
        data = load(session_id)
        data["history"].append({"role": role, "content": content})
        if len(data["history"]) > max_history:
            data["history"] = data["history"][-max_history:]
        save(session_id, data)


def set_active_skills(session_id: str, skills: Set[str]) -> None:
    with _lock:
        data = load(session_id)
        data["active_skills"] = sorted(skills)
        save(session_id, data)


def list_sessions() -> List[str]:
    return [p.stem for p in _SESSIONS_DIR.glob("*.json")]


def delete(session_id: str) -> None:
    try:
        _path(session_id).unlink(missing_ok=True)
    except Exception:
        pass


def _fresh(session_id: str) -> Dict:
    return {
        "session_id":     session_id,
        "history":        [],
        "active_skills":  [],
        "active_agents":  [],
        "curvature_depth": 13,
        "x402_log":       [],
        "mandala_status": "dormant",
    }
