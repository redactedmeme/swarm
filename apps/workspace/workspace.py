"""Per-agent persistent workspace — filesystem + shell.

This is **not** ``apps/exec-runner``. exec-runner is deliberately powerless
(no network, no secrets, no persistence) and stays that way. This service has a
different threat model: a long-lived per-agent container with a real filesystem
and a real shell, so context compounds across tasks. Its containment is:

* **one root per agent** — ``data_dir()/workspace/<agent>``, never shared. Path
  traversal outside that root is rejected.
* **per-agent bearer token** — ``WORKSPACE_TOKEN_<AGENT>`` resolved via
  ``swarm_core.security.secrets``; the request also names the agent and the two
  must agree.
* **egress allowlisted** through ``apps/swarm-egress`` (compose points
  ``HTTPS_PROXY`` at it) — a browser with unrestricted egress is an exfil path.
* **every shell run and filesystem write audited** via
  ``swarm_core.security.audit.record`` with the calling agent as actor.

The dangerous capability is ``workspace.shell`` (network *and* persistence) —
callers must hold it *and* a live approval token; that gate is enforced
agent-side before the request is made, mirroring ``python_exec``.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    from swarm_core.paths import data_dir as _data_dir
except Exception:  # pragma: no cover
    def _data_dir() -> Path:
        return Path(os.getenv("SWARM_DATA_DIR", "/data"))

try:
    from swarm_core.security import audit as _audit
except Exception:  # pragma: no cover
    _audit = None


SHELL_TIMEOUT_DEFAULT = int(os.getenv("WORKSPACE_SHELL_TIMEOUT", "60"))
SHELL_TIMEOUT_MAX = int(os.getenv("WORKSPACE_SHELL_TIMEOUT_MAX", "300"))
SHELL_OUTPUT_CAP = int(os.getenv("WORKSPACE_SHELL_OUTPUT_CAP", str(64 * 1024)))
FILE_READ_CAP = int(os.getenv("WORKSPACE_FILE_READ_CAP", str(512 * 1024)))
FILE_WRITE_CAP = int(os.getenv("WORKSPACE_FILE_WRITE_CAP", str(2 * 1024 * 1024)))


class WorkspaceError(Exception):
    """Raised for a bad request (traversal, missing file, oversize). 400-class."""


@dataclass
class Session:
    """In-memory view of what one agent's workspace is currently doing."""

    agent: str
    started: float = field(default_factory=time.time)
    recent_commands: list[dict] = field(default_factory=list)
    open_pages: dict[str, str] = field(default_factory=dict)   # session -> url

    def note_command(self, cmd: str, exit_code: int) -> None:
        self.recent_commands.append(
            {"cmd": cmd[:200], "exit": exit_code, "ts": round(time.time(), 1)}
        )
        del self.recent_commands[:-25]


_SESSIONS: dict[str, Session] = {}

# ── action traces (routines-from-demonstration, docs/plans grok-bot-parity §7) ──
# One trace = one retrievable sequence of shell / browser / fs actions. An agent
# runs at most one active trace; every audited action is appended to it.
_TRACES: dict[str, dict] = {}          # trace_id -> {agent, name, started, stopped, steps}
_ACTIVE_TRACE: dict[str, str] = {}     # agent -> trace_id
_TRACE_CAP = 500


def trace_start(agent: str, name: str = "") -> str:
    import uuid
    tid = uuid.uuid4().hex
    _TRACES[tid] = {"trace_id": tid, "agent": agent, "name": name or tid[:8],
                    "started": round(time.time(), 1), "stopped": None, "steps": []}
    _ACTIVE_TRACE[agent] = tid
    return tid


def trace_stop(agent: str) -> dict | None:
    tid = _ACTIVE_TRACE.pop(agent, None)
    if not tid:
        return None
    t = _TRACES.get(tid)
    if t:
        t["stopped"] = round(time.time(), 1)
    return t


def trace_get(trace_id: str) -> dict | None:
    return _TRACES.get(trace_id)


def _trace_append(agent: str, action: str, detail: dict) -> None:
    tid = _ACTIVE_TRACE.get(agent)
    if not tid:
        return
    t = _TRACES.get(tid)
    if not t or len(t["steps"]) >= _TRACE_CAP:
        return
    t["steps"].append({"action": action, "detail": detail, "ts": round(time.time(), 2)})


def session_for(agent: str) -> Session:
    s = _SESSIONS.get(agent)
    if s is None:
        s = _SESSIONS[agent] = Session(agent=agent)
    return s


# ── roots + path safety ──────────────────────────────────────────────────────

def agent_root(agent: str) -> Path:
    root = _data_dir() / "workspace" / agent
    root.mkdir(parents=True, exist_ok=True)
    return root


def browser_profile_dir(agent: str) -> Path:
    d = agent_root(agent) / ".browser-profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve(agent: str, rel: str) -> Path:
    """Resolve ``rel`` under the agent root, rejecting any escape."""
    root = agent_root(agent).resolve()
    rel = (rel or "").strip().lstrip("/")
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise WorkspaceError(f"path escapes workspace: {rel!r}")
    return target


def _record(agent: str, event: str, decision: str, detail: dict) -> None:
    _trace_append(agent, event, detail)
    if _audit is None:
        return
    try:
        _audit.record(event, actor=agent, decision=decision,
                      detail={**detail, "trace_id": _ACTIVE_TRACE.get(agent)})
    except Exception:
        pass


# ── filesystem ───────────────────────────────────────────────────────────────

def fs_read(agent: str, path: str) -> dict:
    p = _resolve(agent, path)
    if not p.is_file():
        raise WorkspaceError(f"not a file: {path}")
    if p.stat().st_size > FILE_READ_CAP:
        raise WorkspaceError(f"file too large (> {FILE_READ_CAP} bytes)")
    data = p.read_bytes()
    try:
        text = data.decode("utf-8")
        return {"path": path, "text": text, "bytes": len(data), "encoding": "utf-8"}
    except UnicodeDecodeError:
        import base64
        return {"path": path, "base64": base64.b64encode(data).decode(),
                "bytes": len(data), "encoding": "base64"}


def fs_write(agent: str, path: str, content: str, *, append: bool = False) -> dict:
    if content is None:
        content = ""
    if len(content.encode("utf-8", "ignore")) > FILE_WRITE_CAP:
        raise WorkspaceError(f"content too large (> {FILE_WRITE_CAP} bytes)")
    p = _resolve(agent, path)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(p, mode, encoding="utf-8", newline="") as fh:
        fh.write(content)
    _record(agent, "workspace.fs_write", "allow",
            {"path": path, "bytes": len(content), "append": append})
    return {"path": path, "bytes": len(content), "append": append}


def fs_list(agent: str, path: str = "") -> dict:
    p = _resolve(agent, path)
    if not p.exists():
        raise WorkspaceError(f"no such path: {path}")
    if p.is_file():
        st = p.stat()
        return {"path": path, "entries": [
            {"name": p.name, "type": "file", "size": st.st_size, "mtime": round(st.st_mtime, 1)}
        ]}
    entries = []
    for child in sorted(p.iterdir()):
        st = child.stat()
        entries.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "size": st.st_size,
            "mtime": round(st.st_mtime, 1),
        })
    return {"path": path, "entries": entries}


def _disk_usage(agent: str) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(agent_root(agent)):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


# The container env carries this service's own credentials — every agent's
# WORKSPACE_TOKEN_*, the egress token, and REDIS_URL with the mesh password. The
# shell is agent-facing, so `env` inside it would hand one agent the keys to
# impersonate every other agent and to read the mesh Redis directly. Pass a
# scrubbed environment: an allowlist of inert vars plus the proxy
# settings (whose token only names the caller identity the shell already has,
# and whose destinations the allowlist still constrains).
_ENV_ALLOW = (
    "PATH", "LANG", "LC_ALL", "TZ", "TERM",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
)
def _shell_env(agent: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOW}
    # curl (and libcurl) deliberately ignore the UPPER-case ``HTTP_PROXY`` for
    # ``http://`` URLs — only ``http_proxy`` (lower) is honoured there. The
    # container is configured with the upper-case names, so mirror each proxy
    # var to its opposite case; otherwise plain-HTTP egress from the shell
    # slips past swarm-egress (allowlist + SSRF block + leak scan).
    for up, lo in (("HTTP_PROXY", "http_proxy"),
                   ("HTTPS_PROXY", "https_proxy"),
                   ("NO_PROXY", "no_proxy")):
        if up in env and lo not in env:
            env[lo] = env[up]
        elif lo in env and up not in env:
            env[up] = env[lo]
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env["HOME"] = str(agent_root(agent))
    env["SWARM_AGENT"] = agent
    return env


def _kill_tree(proc) -> None:
    """SIGKILL the command's whole process group, falling back to the shell."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        return
    except (ProcessLookupError, PermissionError, OSError, AttributeError):
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass


# ── shell ────────────────────────────────────────────────────────────────────

async def shell(agent: str, cmd: str, *, timeout: int | None = None, cwd: str = "") -> dict:
    if not cmd or not cmd.strip():
        raise WorkspaceError("empty command")
    timeout = min(int(timeout or SHELL_TIMEOUT_DEFAULT), SHELL_TIMEOUT_MAX)
    workdir = _resolve(agent, cwd) if cwd else agent_root(agent)
    if not workdir.is_dir():
        raise WorkspaceError(f"cwd not a directory: {cwd}")

    # start_new_session puts the shell in its own process group, so a timeout can
    # kill the whole tree. Killing only the shell leaves its children running and
    # holding the pipes open, which makes the second communicate() below block
    # until the command finishes anyway — the timeout would not bound anything.
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=str(workdir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_shell_env(agent),
        start_new_session=True,
    )
    t0 = time.monotonic()
    timed_out = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        _kill_tree(proc)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=5)
        except (asyncio.TimeoutError, Exception):
            out, err = b"", b""

    exit_code = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)
    result = {
        "cmd": cmd,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": out.decode("utf-8", "replace")[:SHELL_OUTPUT_CAP],
        "stderr": err.decode("utf-8", "replace")[:SHELL_OUTPUT_CAP],
        "elapsed_ms": round((time.monotonic() - t0) * 1000),
    }
    session_for(agent).note_command(cmd, exit_code)
    _record(agent, "workspace.shell", "allow" if not timed_out else "block",
            {"cmd": cmd[:200], "exit_code": exit_code, "timed_out": timed_out,
             "elapsed_ms": result["elapsed_ms"]})
    return result


# ── session view ─────────────────────────────────────────────────────────────

def session_view(agent: str) -> dict:
    s = session_for(agent)
    return {
        "agent": agent,
        "root": str(agent_root(agent)),
        "started": round(s.started, 1),
        "uptime_s": round(time.time() - s.started, 1),
        "recent_commands": list(s.recent_commands),
        "open_pages": dict(s.open_pages),
        "disk_bytes": _disk_usage(agent),
    }


def reset_workspace(agent: str) -> dict:
    """Wipe an agent's workspace root (test / operator use). Keeps the dir."""
    root = agent_root(agent)
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    _SESSIONS.pop(agent, None)
    _record(agent, "workspace.reset", "allow", {"root": str(root)})
    return {"agent": agent, "reset": True}
