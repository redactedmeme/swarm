"""swarm-egress — the swarm's outbound network chokepoint (IronClaw control 3).

A small asyncio forward proxy. Every agent container sets
``HTTPS_PROXY=http://127.0.0.1:8891`` (host network) and authenticates with
``Proxy-Authorization: Bearer <EGRESS_TOKEN_*>``. For each request the host is
checked against that caller's allowlist in ``swarm_core.security.egress`` — a
compromised or prompt-injected agent can no longer reach ``evil.com`` or the
residential IP's neighbours.

Coverage:
* ``CONNECT`` (HTTPS)  — host allowlist + SSRF block, then an opaque tunnel.
  Bodies are TLS-encrypted end to end, so leak scanning happens at the app layer
  (the LLM path already goes through ``apps/proxy``); this stops the destination.
* absolute-form HTTP    — host allowlist, plus ``leakscan`` of the request line
  and headers (block on a ``block``-severity secret) and best-effort credential
  injection for hosts with an ``inject:`` rule.

Every decision is written to the tamper-evident audit log (denies always,
allows sampled).
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import random
import re

from swarm_core.security import egress, leakscan

try:
    from swarm_core.security import audit as _audit
except Exception:  # pragma: no cover
    _audit = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("swarm-egress")

HOST = os.getenv("EGRESS_BIND", "127.0.0.1")
PORT = int(os.getenv("EGRESS_PORT", "8891"))
UPSTREAM = os.getenv("EGRESS_UPSTREAM_PROXY", "")  # optional: chain to gluetun/Mullvad
IDLE_TIMEOUT = int(os.getenv("EGRESS_IDLE_TIMEOUT", "120"))

_REQ_LINE = re.compile(r"^(?P<method>[A-Z]+)\s+(?P<target>\S+)\s+HTTP/(?P<ver>1\.[01])\r?$")


def _audit_decision(event: str, d: egress.Decision, host: str, extra: dict | None = None) -> None:
    if _audit is None:
        return
    if d.allow and random.random() > 0.05:  # sample allows at 5%
        return
    try:
        _audit.record(event, actor=f"egress:{d.caller}", decision="allow" if d.allow else "deny",
                      severity="info" if d.allow else "warning",
                      detail={"host": host, "reason": d.reason, **(extra or {})})
    except Exception:
        pass


def _proxy_token(value: str) -> str:
    """Accept ``Bearer <tok>`` or ``Basic base64(user:tok)`` — HTTP client libs
    only emit Proxy-Authorization when the proxy URL carries credentials, and
    they send Basic. The token is the password half (or the whole thing)."""
    value = value.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    if value.lower().startswith("basic "):
        try:
            raw = base64.b64decode(value[6:].strip()).decode("latin1")
            return raw.split(":", 1)[1] if ":" in raw else raw
        except (binascii.Error, ValueError):
            return ""
    return value


def _parse_headers(blob: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in blob.split(b"\r\n")[1:]:
        if b":" in line:
            k, _, v = line.partition(b":")
            out[k.decode("latin1").strip().lower()] = v.decode("latin1").strip()
    return out


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(65536), timeout=IDLE_TIMEOUT)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _deny(writer: asyncio.StreamWriter, code: int, msg: str) -> None:
    writer.write(f"HTTP/1.1 {code} {msg}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
    try:
        await writer.drain()
    except Exception:
        pass
    writer.close()


async def handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
    peer = client_w.get_extra_info("peername")
    try:
        head = await asyncio.wait_for(client_r.readuntil(b"\r\n\r\n"), timeout=15)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        client_w.close()
        return

    first, _, _ = head.partition(b"\r\n")
    m = _REQ_LINE.match(first.decode("latin1"))
    if not m:
        await _deny(client_w, 400, "Bad Request")
        return

    headers = _parse_headers(head)
    token = _proxy_token(headers.get("proxy-authorization", ""))
    pol = egress.load()

    method, target = m.group("method"), m.group("target")

    # ── HTTPS: CONNECT host:port ──────────────────────────────────────────
    if method == "CONNECT":
        host, _, port_s = target.partition(":")
        port = int(port_s or 443)
        d = pol.decide(host, token)
        _audit_decision("egress.connect", d, host, {"port": port})
        if not d.allow:
            log.warning("DENY CONNECT %s (%s) caller=%s", host, d.reason, d.caller)
            await _deny(client_w, 403, "Forbidden by egress policy")
            return
        try:
            up_r, up_w = await asyncio.wait_for(
                asyncio.open_connection(*_upstream_target(host, port)), timeout=15
            )
            if UPSTREAM:
                up_w.write(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
                await up_w.drain()
                await up_r.readuntil(b"\r\n\r\n")
        except Exception as e:
            await _deny(client_w, 502, "Bad Gateway")
            log.warning("CONNECT %s upstream failed: %s", host, e)
            return
        client_w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_w.drain()
        await asyncio.gather(_pipe(client_r, up_w), _pipe(up_r, client_w))
        return

    # ── Plaintext HTTP: absolute-form target ─────────────────────────────
    mt = re.match(r"http://([^/]+)(/.*)?$", target)
    if not mt:
        await _deny(client_w, 400, "Only absolute-form http/https via this proxy")
        return
    hostport, path = mt.group(1), mt.group(2) or "/"
    host = hostport.split(":")[0]
    port = int(hostport.split(":")[1]) if ":" in hostport else 80

    d = pol.decide(host, token)
    _audit_decision("egress.http", d, host, {"method": method})
    if not d.allow:
        log.warning("DENY %s http://%s (%s) caller=%s", method, host, d.reason, d.caller)
        await _deny(client_w, 403, "Forbidden by egress policy")
        return

    body = b""
    clen = int(headers.get("content-length", "0") or 0)
    if clen:
        try:
            body = await asyncio.wait_for(client_r.readexactly(clen), timeout=30)
        except Exception:
            body = b""

    scan_target = first.decode("latin1") + "\n" + head.decode("latin1") + "\n" + body[:8192].decode("latin1", "ignore")
    hits = leakscan.scan(scan_target)
    if leakscan.worst(hits) == "block":
        if _audit is not None:
            try:
                _audit.record("egress.leak_block", actor=f"egress:{d.caller}", decision="block",
                              severity="warning", detail={"host": host, "rules": [h.rule for h in hits]})
            except Exception:
                pass
        log.warning("DENY %s http://%s — outbound secret (%s)", method, host, [h.rule for h in hits])
        await _deny(client_w, 451, "Blocked: outbound secret detected")
        return

    try:
        up_r, up_w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=15)
    except Exception:
        await _deny(client_w, 502, "Bad Gateway")
        return

    # rebuild an origin-form request; drop hop-by-hop + proxy auth headers
    drop = {"proxy-authorization", "proxy-connection", "connection", "keep-alive", "te", "trailer", "upgrade"}
    lines = [f"{method} {path} HTTP/1.1"]
    seen_host = False
    for line in head.split(b"\r\n")[1:]:
        if not line or b":" not in line:
            continue
        k = line.split(b":", 1)[0].decode("latin1").strip().lower()
        if k in drop:
            continue
        if k == "host":
            seen_host = True
        lines.append(line.decode("latin1"))
    if not seen_host:
        lines.append(f"Host: {host}")
    lines.append("Connection: close")
    up_w.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin1") + body)
    await up_w.drain()
    await _pipe(up_r, client_w)


def _upstream_target(host: str, port: int) -> tuple[str, int]:
    if UPSTREAM:
        u = UPSTREAM.removeprefix("http://").removeprefix("https://")
        h, _, p = u.partition(":")
        return h, int(p or 8888)
    return host, port


async def main() -> None:
    egress.load()
    server = await asyncio.start_server(handle, HOST, PORT)
    log.info("swarm-egress on %s:%s  upstream=%s", HOST, PORT, UPSTREAM or "direct")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
