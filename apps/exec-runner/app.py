"""exec-runner — the swarm's code-execution sandbox (IronClaw control 1).

A tiny aiohttp service that accepts ``POST /run {"code": "...", "timeout": N}``
and executes it via ``runner.run_code`` inside this deliberately powerless
container:

* no secrets in the environment (compose gives it no ``env_file``)
* ``network_mode: none`` — the snippet cannot reach the LLM proxy, Redis,
  wallets, or the internet
* listens on a **unix domain socket** on a shared volume, not a TCP port
  (a no-network container can't bind one) — callers mount the same volume

The only clients are swarm agents on the same box; auth is a shared bearer token
(``EXEC_RUNNER_TOKEN``) checked in constant time, plus the socket's filesystem
permissions. Every run is audited by the caller (it holds the actor identity);
this service also logs a one-line summary.
"""
from __future__ import annotations

import hmac
import logging
import os
import time

from aiohttp import web

import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("exec-runner")

SOCK = os.getenv("EXEC_RUNNER_SOCK", "/run/exec/exec.sock")
TOKEN = os.getenv("EXEC_RUNNER_TOKEN", "")
MAX_BODY = 512 * 1024


def _authorized(request: web.Request) -> bool:
    if not TOKEN:
        return True  # socket-perms-only mode (dev)
    got = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(got, TOKEN)


async def handle_run(request: web.Request) -> web.Response:
    if not _authorized(request):
        return web.json_response({"status": "error", "error": "unauthorized"}, status=401)
    if request.content_length and request.content_length > MAX_BODY:
        return web.json_response({"status": "error", "error": "body too large"}, status=413)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"status": "error", "error": "invalid JSON"}, status=400)

    code = body.get("code", "")
    timeout = body.get("timeout", runner.MAX_WALL_SECONDS)
    t0 = time.monotonic()
    result = await runner.run_code(code, timeout)
    result["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
    log.info(
        "run status=%s exit=%s elapsed=%sms jail=%s bytes=%s",
        result.get("status"), result.get("exit_code"), result["elapsed_ms"],
        result.get("jail"), len(code or ""),
    )
    return web.json_response(result)


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "jail": "nsjail" if runner._NSJAIL else "rlimit"})


def build_app() -> web.Application:
    app = web.Application(client_max_size=MAX_BODY)
    app.router.add_post("/run", handle_run)
    app.router.add_get("/health", handle_health)
    return app


if __name__ == "__main__":
    os.makedirs(os.path.dirname(SOCK), exist_ok=True)
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    log.info("exec-runner listening on %s (auth=%s, jail=%s)",
             SOCK, "token" if TOKEN else "socket-perms", "nsjail" if runner._NSJAIL else "rlimit")
    web.run_app(build_app(), path=SOCK, print=None)
    try:
        os.chmod(SOCK, 0o660)
    except OSError:
        pass
