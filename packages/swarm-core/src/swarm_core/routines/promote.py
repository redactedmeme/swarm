"""Trace -> skill doc + routine spec + scheduled replay."""
from __future__ import annotations

import http.client
import json
import logging
import os
import re
import socket
import time
from pathlib import Path
from typing import Any, Iterable

try:
    from swarm_core.paths import data_dir as _data_dir
except Exception:  # pragma: no cover
    def _data_dir() -> Path:
        return Path(os.getenv("SWARM_DATA_DIR", "/data"))

log = logging.getLogger("swarm_core.routines")

# Trace actions that can be deterministically replayed and how they map onto the
# workspace HTTP API. type/screenshot/fs_write are *recorded* but replay needs an
# explicit value the recorder deliberately does not keep (typed text, file body).
_REPLAYABLE = {
    "workspace.shell": ("/shell", ("cmd", "cwd", "timeout")),
    "workspace.browser_goto": ("/browser/goto", ("url", "session")),
    "workspace.browser_click": ("/browser/click", ("selector", "session")),
}
_RECORDED_NOT_REPLAYABLE = {
    "workspace.browser_type", "workspace.browser_screenshot", "workspace.fs_write",
}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return s or f"routine_{int(time.time())}"


def skills_dir() -> Path:
    d = _data_dir() / "skills"
    d.mkdir(parents=True, exist_ok=True)
    return d


def routines_dir() -> Path:
    d = _data_dir() / "routines"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── distillation ─────────────────────────────────────────────────────────────

def _step_line(step: dict) -> str:
    action = step.get("action", "?")
    d = step.get("detail") or {}
    if action == "workspace.shell":
        return f"`$ {d.get('cmd', '')}`"
    if action == "workspace.browser_goto":
        return f"open {d.get('url', '')}"
    if action == "workspace.browser_click":
        return f"click `{d.get('selector', '')}`"
    if action == "workspace.browser_type":
        return f"type into `{d.get('selector', '')}` ({d.get('chars', 0)} chars — value not recorded)"
    if action == "workspace.browser_screenshot":
        return "screenshot"
    if action == "workspace.fs_write":
        return f"write `{d.get('path', '')}` ({d.get('bytes', 0)} bytes — body not recorded)"
    return f"{action} {json.dumps(d, sort_keys=True)[:120]}"


def distill_skill_doc(name: str, description: str, steps: Iterable[dict]) -> str:
    """Render the standard skill markdown from a trace. Pure string, no LLM."""
    steps = list(steps)
    numbered = "\n".join(f"{i}. {_step_line(s)}" for i, s in enumerate(steps, 1)) or "1. (empty trace)"
    first_cmds = [s["detail"].get("cmd", "") for s in steps
                  if s.get("action") == "workspace.shell" and (s.get("detail") or {}).get("cmd")]
    example = first_cmds[0] if first_cmds else "(replay the recorded steps)"
    return (
        f"# {name}\n\n"
        f"## Description\n{description or 'Routine distilled from a recorded workspace action trace.'}\n\n"
        f"## When to Use\n"
        f"- The same multi-step workspace task recurs and the steps below still apply.\n"
        f"- Re-run on a schedule via `swarm_core.routines` / `SwarmScheduler`.\n\n"
        f"## Steps\n{numbered}\n\n"
        f"## Example\nInput: (scheduled, no input)\n"
        f"Output: replays {len(steps)} step(s); first action: `{example}`\n"
    )


# ── promotion ────────────────────────────────────────────────────────────────

def promote(
    trace: list[dict],
    *,
    name: str,
    interval_s: int,
    description: str = "",
    agent: str = "hermes",
    priority: int = 3,
    overrides: dict[int, dict] | None = None,
) -> dict:
    """Write a skill doc + a routine spec. Returns paths + the routine id.

    ``overrides`` supplies values the recorder does not keep, keyed by 1-based
    step index: ``{3: {"text": "..."}}`` for a ``browser_type`` step,
    ``{5: {"content": "..."}}`` for an ``fs_write`` step.
    """
    if interval_s < 60:
        raise ValueError("interval_s must be >= 60")
    slug = slugify(name)
    steps = list(trace or [])

    doc = distill_skill_doc(name, description, steps)
    skill_path = skills_dir() / f"{slug}.md"
    skill_path.write_text(doc, encoding="utf-8")

    spec = {
        "id": f"routine_{slug}",
        "name": name,
        "slug": slug,
        "agent": agent,
        "interval_s": int(interval_s),
        "priority": int(priority),
        "created": round(time.time(), 1),
        "skill_doc": f"skills/{slug}.md",
        "steps": _prepare_steps(steps, overrides or {}),
    }
    spec_path = routines_dir() / f"{slug}.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    log.info("routine promoted: %s (%d steps, every %ds)", slug, len(spec["steps"]), interval_s)
    return {"routine_id": spec["id"], "slug": slug,
            "skill_path": str(skill_path), "spec_path": str(spec_path),
            "replayable_steps": sum(1 for s in spec["steps"] if s.get("replayable"))}


def _prepare_steps(steps: list[dict], overrides: dict[int, dict]) -> list[dict]:
    out = []
    for i, s in enumerate(steps, 1):
        action = s.get("action", "")
        d = dict(s.get("detail") or {})
        d.update(overrides.get(i, {}))
        replayable = action in _REPLAYABLE
        if action == "workspace.browser_type" and "text" in d:
            replayable = True
        if action == "workspace.fs_write" and "content" in d:
            replayable = True
        out.append({"action": action, "detail": d, "replayable": replayable})
    return out


# ── replay ───────────────────────────────────────────────────────────────────

class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, sock_path: str, timeout: int = 120):
        super().__init__("localhost", timeout=timeout)
        self._sock_path = sock_path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._sock_path)
        self.sock = s


def _ws_call(path: str, body: dict, *, agent: str) -> dict:
    sock = os.getenv("WORKSPACE_SOCK", "/run/workspace/workspace.sock")
    token = (os.getenv("WORKSPACE_TOKEN_" + agent.upper().replace("-", "_")) or "").strip()
    conn = _UnixHTTPConnection(sock)
    headers = {"Content-Type": "application/json", "X-Swarm-Agent": agent,
               "Authorization": f"Bearer {token}"}
    try:
        conn.request("POST", path, body=json.dumps(body), headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"status": "error", "error": raw[:200]}
    finally:
        conn.close()


def run_routine(spec: dict) -> dict:
    """Replay a routine spec's steps against the workspace socket.

    Stops at the first failing step. type/screenshot/fs_write steps without an
    explicit value are skipped (the recorder does not keep typed text or file
    bodies) and noted, not treated as failures.
    """
    agent = spec.get("agent", "hermes")
    results = []
    for n, step in enumerate(spec.get("steps", []), 1):
        action = step.get("action", "")
        d = step.get("detail") or {}
        if action in _REPLAYABLE:
            api, fields = _REPLAYABLE[action]
            payload = {k: d[k] for k in fields if k in d}
            r = _ws_call(api, payload, agent=agent)
        elif action == "workspace.browser_type" and "text" in d:
            r = _ws_call("/browser/type", {"selector": d.get("selector", ""),
                                           "text": d["text"], "session": d.get("session", "default")},
                         agent=agent)
        elif action == "workspace.fs_write" and "content" in d:
            r = _ws_call("/fs/write", {"path": d.get("path", ""), "content": d["content"],
                                       "append": bool(d.get("append"))}, agent=agent)
        else:
            results.append({"step": n, "action": action, "status": "skipped",
                            "reason": "no recorded value to replay"})
            continue
        status = r.get("status", "error")
        results.append({"step": n, "action": action, "status": status,
                        "error": r.get("error")})
        if status not in ("ok",):
            return {"routine": spec.get("id"), "ran": n, "ok": False, "results": results}
    return {"routine": spec.get("id"), "ran": len(results), "ok": True, "results": results}


# ── scheduler bridge ─────────────────────────────────────────────────────────

def load_routines() -> list[Any]:
    """Read routine specs as ``swarm_scheduler.SwarmTask``s. Safe to call when
    the scheduler module is unavailable (returns [])."""
    try:
        from swarm_core.swarm_scheduler import SwarmTask
    except Exception:  # pragma: no cover
        return []

    tasks = []
    for spec_path in sorted(routines_dir().glob("*.json")):
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            log.warning("routine spec %s unreadable: %s", spec_path.name, e)
            continue

        def _factory(_spec=spec):
            async def _run():
                import asyncio
                return await asyncio.get_event_loop().run_in_executor(None, run_routine, _spec)
            return _run()

        tasks.append(SwarmTask(
            id=spec.get("id", f"routine_{spec_path.stem}"),
            name=f"Routine: {spec.get('name', spec_path.stem)}",
            coro_factory=_factory,
            interval_s=int(spec.get("interval_s", 3600)),
            priority=int(spec.get("priority", 3)),
            tags=["routine", "demonstration"],
        ))
    return tasks
