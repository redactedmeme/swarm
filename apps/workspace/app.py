"""workspace — the swarm's persistent per-agent computer (fs + shell + browser).

A small aiohttp service on a **unix domain socket** (``WORKSPACE_SOCK``), the
same transport shape as ``apps/exec-runner`` so callers already know it. Unlike
exec-runner this container *is* powerful (network + persistence), so its
containment is identity + audit + egress allowlist rather than a powerless jail:

* **per-agent bearer token** — the request carries ``X-Swarm-Agent: <agent>``
  and ``Authorization: Bearer <token>``; the token must equal
  ``WORKSPACE_TOKEN_<AGENT>`` (resolved via ``swarm_core.security.secrets``),
  compared with ``hmac.compare_digest``.
* each agent gets its own root (``data_dir()/workspace/<agent>``) and its own
  browser profile — never shared. See §11 of ``docs/plans/grok-bot-parity.md``.
* every ``/shell`` and ``/browser`` action and every ``/fs/write`` is audited.

Endpoints:
  POST /fs/read      {path}                     -> file contents
  POST /fs/write     {path, content, append?}   -> ok
  POST /fs/list      {path?}                     -> entries
  POST /shell        {cmd, timeout?, cwd?}       -> stdout/stderr/exit_code
  POST /browser/goto {url, session?}
  POST /browser/read {session?, max_chars?}
  POST /browser/click|type|screenshot|session
  GET  /session                                 -> open pages, recent cmds, disk use
  GET  /health
"""
from __future__ import annotations

import hmac
import logging
import os

from aiohttp import web

import browser as _browser
import workspace as _ws

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("workspace")

SOCK = os.getenv("WORKSPACE_SOCK", "/run/workspace/workspace.sock")
_SAFE_AGENT_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_BODY = 4 * 1024 * 1024

try:
    from swarm_core.security.identity import AgentId as _AgentId
except Exception:  # pragma: no cover
    _AgentId = None

try:
    from swarm_core.security.secrets import get_secret as _get_secret
except Exception:  # pragma: no cover
    def _get_secret(name, default=None, *, required=False):
        return os.getenv(name, default)


def _token_for(agent: str) -> str:
    env = "WORKSPACE_TOKEN_" + agent.upper().replace("-", "_")
    return (_get_secret(env) or "").strip()


def _auth(request: web.Request) -> str:
    """Return the authenticated agent name, or raise HTTPUnauthorized."""
    agent = (request.headers.get("X-Swarm-Agent") or "").strip().lower()
    got = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not agent or not got:
        raise web.HTTPUnauthorized(text="missing X-Swarm-Agent or bearer token")
    # The name is used to build an env var name and a filesystem root, so it has
    # to be validated here rather than trusted from the header.
    if not _SAFE_AGENT_RE.match(agent):
        raise web.HTTPUnauthorized(text="invalid agent name")
    if _AgentId is not None:
        try:
            agent = str(_AgentId(agent))
        except Exception:
            raise web.HTTPUnauthorized(text="unknown agent")
    want = _token_for(agent)
    if not want or not hmac.compare_digest(got, want):
        raise web.HTTPUnauthorized(text="bad token for agent")
    return agent


async def _json(request: web.Request) -> dict:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        raise web.HTTPBadRequest(text="invalid JSON")


def _ok(payload: dict) -> web.Response:
    return web.json_response(payload)


def _bad(e: Exception, status: int = 400) -> web.Response:
    return web.json_response({"status": "error", "error": str(e)}, status=status)


# ── filesystem ───────────────────────────────────────────────────────────────

async def h_fs_read(request):
    agent = _auth(request)
    body = await _json(request)
    try:
        return _ok({"status": "ok", **_ws.fs_read(agent, body.get("path", ""))})
    except _ws.WorkspaceError as e:
        return _bad(e)


async def h_fs_write(request):
    agent = _auth(request)
    body = await _json(request)
    try:
        return _ok({"status": "ok", **_ws.fs_write(
            agent, body.get("path", ""), body.get("content", ""),
            append=bool(body.get("append")))})
    except _ws.WorkspaceError as e:
        return _bad(e)


async def h_fs_list(request):
    agent = _auth(request)
    body = await _json(request)
    try:
        return _ok({"status": "ok", **_ws.fs_list(agent, body.get("path", ""))})
    except _ws.WorkspaceError as e:
        return _bad(e)


# ── shell ────────────────────────────────────────────────────────────────────

async def h_shell(request):
    agent = _auth(request)
    body = await _json(request)
    try:
        result = await _ws.shell(agent, body.get("cmd", ""),
                                 timeout=body.get("timeout"), cwd=body.get("cwd", ""))
        return _ok({"status": "ok", **result})
    except _ws.WorkspaceError as e:
        return _bad(e)


# ── browser ──────────────────────────────────────────────────────────────────

async def h_browser_goto(request):
    agent = _auth(request)
    body = await _json(request)
    return _ok(await _browser.goto(agent, body.get("url", ""), body.get("session", "default")))


async def h_browser_read(request):
    agent = _auth(request)
    body = await _json(request)
    return _ok(await _browser.read(agent, body.get("session", "default"),
                                   max_chars=int(body.get("max_chars") or 8000)))


async def h_browser_click(request):
    agent = _auth(request)
    body = await _json(request)
    return _ok(await _browser.click(agent, body.get("selector", ""), body.get("session", "default")))


async def h_browser_type(request):
    agent = _auth(request)
    body = await _json(request)
    return _ok(await _browser.type_text(agent, body.get("selector", ""),
                                        body.get("text", ""), body.get("session", "default")))


async def h_browser_screenshot(request):
    agent = _auth(request)
    body = await _json(request)
    return _ok(await _browser.screenshot(agent, body.get("session", "default")))


async def h_browser_session(request):
    agent = _auth(request)
    return _ok(await _browser.session_info(agent))


# ── session + health ─────────────────────────────────────────────────────────

async def h_session(request):
    agent = _auth(request)
    return _ok({"status": "ok", **_ws.session_view(agent)})


# ── traces (routines from demonstration) ─────────────────────────────────────

async def h_trace_start(request):
    agent = _auth(request)
    body = await _json(request)
    tid = _ws.trace_start(agent, body.get("name", ""))
    return _ok({"status": "ok", "trace_id": tid})


async def h_trace_stop(request):
    agent = _auth(request)
    t = _ws.trace_stop(agent)
    if t is None:
        return _ok({"status": "ok", "trace_id": None, "steps": 0})
    return _ok({"status": "ok", "trace_id": t["trace_id"], "steps": len(t["steps"])})


async def h_trace_get(request):
    agent = _auth(request)
    t = _ws.trace_get(request.match_info["trace_id"])
    if not t:
        return web.json_response({"status": "error", "error": "no such trace"}, status=404)
    if t.get("agent") != agent:
        raise web.HTTPUnauthorized(text="trace belongs to another agent")
    return _ok({"status": "ok", **t})


async def h_health(_request):
    have_pw = False
    try:
        import playwright  # noqa: F401
        have_pw = True
    except Exception:
        pass
    return web.json_response({"status": "ok", "browser": have_pw})


def build_app() -> web.Application:
    app = web.Application(client_max_size=MAX_BODY)
    app.router.add_post("/fs/read", h_fs_read)
    app.router.add_post("/fs/write", h_fs_write)
    app.router.add_post("/fs/list", h_fs_list)
    app.router.add_post("/shell", h_shell)
    app.router.add_post("/browser/goto", h_browser_goto)
    app.router.add_post("/browser/read", h_browser_read)
    app.router.add_post("/browser/click", h_browser_click)
    app.router.add_post("/browser/type", h_browser_type)
    app.router.add_post("/browser/screenshot", h_browser_screenshot)
    app.router.add_post("/browser/session", h_browser_session)
    app.router.add_get("/session", h_session)
    app.router.add_post("/trace/start", h_trace_start)
    app.router.add_post("/trace/stop", h_trace_stop)
    app.router.add_get("/trace/{trace_id}", h_trace_get)
    app.router.add_get("/health", h_health)
    return app


def _bind_socket(path: str):
    """Bind the unix socket ourselves so its mode is right *before* anything can
    connect. aiohttp's on_startup hook runs before ``run_app`` creates the site,
    so a chmod there has no socket to act on, and after ``run_app`` returns the
    server is already shutting down. 0o660 is what keeps the caller set to the
    containers that share the volume."""
    import socket as _socket
    import stat as _stat

    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.unlink(path)
    sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    old_umask = os.umask(0o177)
    try:
        sock.bind(path)
    finally:
        os.umask(old_umask)
    os.chmod(path, stat_mode := (_stat.S_IRUSR | _stat.S_IWUSR | _stat.S_IRGRP | _stat.S_IWGRP))
    log.info("workspace socket %s mode %o", path, stat_mode)
    sock.listen(128)
    return sock


if __name__ == "__main__":  # pragma: no cover
    app = build_app()
    listener = _bind_socket(SOCK)
    log.info("workspace listening on %s", SOCK)
    web.run_app(app, sock=listener, print=None)
