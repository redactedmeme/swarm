"""Capability model + staged authorization (IronClaw control 7).

IronClaw keeps "authorization, approval, dispatch, and execution [as] distinct
stages — never collapsed or bypassed", with capability-based permissions.

This module gives the swarm the same shape without a rewrite:

    from swarm_core.security import authz

    authz.require("hermes", "code.exec")          # raises Denied if not granted
    if authz.allowed("smolting", "funds.transfer"): ...

    # staged: a high-risk capability needs an explicit approval token
    tok = authz.request_approval("hermes", "infra.deploy", detail={...})
    ...            # operator / committee approves out of band
    authz.require("hermes", "infra.deploy", approval=tok)

Grants load from ``caps.yaml``. High-risk capabilities (``exec``, ``funds``,
``infra deploy``, ``secret read``, ``docker``) are listed under ``requires_approval``
and cannot be satisfied by a static grant alone — ``require`` rejects them unless
a live, matching approval token is passed. Approval tokens live in Redis (short
TTL) so the Sevenfold Committee path and the Telegram-admin path can both mint
them; without Redis they fall back to an in-process store (single-agent use).

``ADMIN_IDS`` handling is **fail-closed**: ``is_admin(agent, user_id)`` returns
False when no admins are configured (the old bots returned True).
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

from .identity import AgentId

log = logging.getLogger(__name__)


class Denied(PermissionError):
    """Raised by ``require``. ``.capability`` / ``.actor`` / ``.reason`` are set."""

    def __init__(self, actor: str, capability: str, reason: str):
        self.actor, self.capability, self.reason = actor, capability, reason
        super().__init__(f"{actor} denied '{capability}': {reason}")


# ── policy ───────────────────────────────────────────────────────────────────
_DEFAULT_POLICY: dict[str, Any] = {
    # `code.exec` is deliberately NOT here: apps/exec-runner (no secrets, no
    # network, rlimited) IS the control for it, so the static grant is enough.
    # These are the capabilities where containment isn't possible and a human /
    # committee must sign off each time.
    "requires_approval": [
        "funds.transfer",
        "infra.deploy",
        "secret.read",
        "docker.control",
        "inbox.broadcast_admin",
        "social.post",
        "workspace.shell",
    ],
    "grants": {
        # agent -> capabilities it may hold. "*" = any capability (still subject
        # to the approval gate for requires_approval entries).
        "hermes": ["code.exec", "infra.deploy", "secret.read", "web.fetch", "inbox.send", "llm.call", "social.post", "workspace.shell", "workspace.browse", "evolve.promote"],
        "redactedbuilder": ["funds.transfer", "web.fetch", "inbox.send", "llm.call"],
        "redactedintern": ["infra.deploy", "inbox.send", "llm.call"],
        "redactedgovimprover": ["inbox.send", "llm.call"],
        "smolting": ["web.fetch", "inbox.send", "llm.call", "workspace.browse", "evolve.promote"],
        "runtime": ["web.fetch", "inbox.send", "llm.call"],
        "redacted-chan": ["inbox.send", "llm.call", "web.fetch", "workspace.browse", "workspace.shell", "infra.deploy", "code.exec", "evolve.promote"],
        "mandalaasettler": ["funds.transfer", "inbox.send", "llm.call"],
        "refinery": ["inbox.send", "llm.call"],
    },
    # agent -> capabilities that skip the approval gate for that agent only. Use
    # sparingly: the agent still needs the static grant, and the exemption is
    # recorded in caps.yaml where it can be audited. redacted-chan is a trusted
    # private companion with no outward publishing surface, so her workspace
    # shell is always-on (same ergonomics as her sandboxed python_exec).
    "approval_exempt": {
        "redacted-chan": ["workspace.shell"],
    },
    "approval_ttl": 900,
}

_POLICY: dict[str, Any] = {}


def _load_policy() -> None:
    global _POLICY
    _POLICY = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in _DEFAULT_POLICY.items()}
    path = Path(__file__).with_name("caps.yaml")
    if path.exists():
        try:
            import yaml

            doc = yaml.safe_load(path.read_text("utf-8")) or {}
            for key in ("requires_approval", "grants", "approval_exempt", "approval_ttl"):
                if key in doc and doc[key] is not None:
                    _POLICY[key] = doc[key]
        except Exception as exc:  # pragma: no cover
            log.warning("authz: using built-in policy (%s)", exc)


_load_policy()


def reload_policy() -> None:
    _load_policy()


# ── approval token store ─────────────────────────────────────────────────────
_mem_tokens: dict[str, dict[str, Any]] = {}
_redis = None
_redis_tried = False


def _get_redis():
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    url = os.getenv("REDIS_URL", "")
    if url:
        try:
            import redis as _r

            _redis = _r.from_url(url, decode_responses=True, socket_connect_timeout=2)
            _redis.ping()
        except Exception as exc:  # pragma: no cover
            log.warning("authz: approval tokens are in-process only (%s)", exc)
            _redis = None
    return _redis


def _tok_key(tok: str) -> str:
    return f"authz:approval:{tok}"


# Index of not-yet-resolved approvals, so a human surface (Telegram admin DM,
# the Field Kit board) can enumerate what is waiting. Score = expiry epoch, so
# expired entries reap on read. Entries are removed on grant / deny / expiry.
_PENDING_INDEX = "authz:approval:pending"
_EVENT_STREAM = "swarm:approvals:events"


def _redacted_summary(rec: dict[str, Any]) -> str:
    """A short, non-sensitive description of a requested action."""
    d = rec.get("detail") or {}
    for k in ("summary", "reason", "target", "action"):
        v = d.get(k)
        if isinstance(v, str) and v:
            return v[:200]
    return f"{rec.get('capability', '?')} requested by {rec.get('actor', '?')}"


def _publish_event(kind: str, tok: str, rec: dict[str, Any]) -> None:
    """Best-effort notify surface. Never raises."""
    payload = {
        "kind": kind,
        "token": tok,
        "actor": rec.get("actor"),
        "capability": rec.get("capability"),
        "summary": _redacted_summary(rec),
        "created": rec.get("created"),
        "expires": rec.get("created", time.time()) + int(_POLICY["approval_ttl"]),
    }
    try:
        from . import audit as _audit

        _audit.record("authz.approval", actor=str(rec.get("actor", "unknown")),
                      decision={"requested": "pending", "granted": "allow",
                                "denied": "deny"}.get(kind, "pending"),
                      severity="warning" if kind != "granted" else "info",
                      detail={"token": tok[:6], "capability": rec.get("capability"),
                              "summary": payload["summary"]})
    except Exception:
        pass
    r = _get_redis()
    if r is not None:
        try:
            import json as _j

            r.lpush(_EVENT_STREAM, _j.dumps(payload))
            r.ltrim(_EVENT_STREAM, 0, 199)
        except Exception:  # pragma: no cover
            pass


def request_approval(actor: str, capability: str, *, detail: dict | None = None) -> str:
    """Mint a pending approval and return its token. The token is *not* yet
    valid — an approver must call ``grant_approval(token)``.
    """
    actor = str(AgentId(actor))
    tok = secrets.token_urlsafe(18)
    rec = {
        "actor": actor,
        "capability": capability,
        "state": "pending",
        "detail": detail or {},
        "created": time.time(),
    }
    ttl = int(_POLICY["approval_ttl"])
    r = _get_redis()
    if r is not None:
        import json as _j

        r.set(_tok_key(tok), _j.dumps(rec), ex=ttl)
        try:
            r.zadd(_PENDING_INDEX, {tok: rec["created"] + ttl})
        except Exception:  # pragma: no cover
            pass
    else:
        _mem_tokens[tok] = rec
    log.info("authz: approval requested actor=%s cap=%s tok=%s", actor, capability, tok[:6])
    _publish_event("requested", tok, rec)
    return tok


def _deindex(tok: str) -> None:
    r = _get_redis()
    if r is not None:
        try:
            r.zrem(_PENDING_INDEX, tok)
        except Exception:  # pragma: no cover
            pass


def grant_approval(tok: str, *, approver: str = "operator") -> bool:
    rec = _read_token(tok)
    if not rec or rec.get("state") != "pending":
        return False
    rec["state"] = "granted"
    rec["approver"] = approver
    _write_token(tok, rec)
    _deindex(tok)
    _publish_event("granted", tok, rec)
    return True


def deny_approval(tok: str, *, approver: str = "operator", reason: str = "") -> bool:
    """Explicit denial. Expiry is *also* a denial (the token simply vanishes),
    but this lets a human reject immediately and record why."""
    rec = _read_token(tok)
    if not rec or rec.get("state") != "pending":
        return False
    rec["state"] = "denied"
    rec["approver"] = approver
    rec["deny_reason"] = reason[:200]
    _write_token(tok, rec)
    _deindex(tok)
    _publish_event("denied", tok, rec)
    return True


def list_pending_approvals() -> list[dict[str, Any]]:
    """Enumerate unresolved approvals for a human surface. Reaps expired
    entries. Returns redacted records — no raw ``detail`` payloads."""
    r = _get_redis()
    now = time.time()
    out: list[dict[str, Any]] = []
    if r is not None:
        try:
            toks = r.zrange(_PENDING_INDEX, 0, -1)
        except Exception:  # pragma: no cover
            toks = []
        stale: list[str] = []
        for tok in toks:
            rec = _read_token(tok)
            if not rec or rec.get("state") != "pending":
                stale.append(tok)
                continue
            out.append({
                "token": tok,
                "actor": rec.get("actor"),
                "capability": rec.get("capability"),
                "summary": _redacted_summary(rec),
                "created": rec.get("created"),
                "expires": rec.get("created", now) + int(_POLICY["approval_ttl"]),
            })
        if stale:
            try:
                r.zrem(_PENDING_INDEX, *stale)
            except Exception:  # pragma: no cover
                pass
        return sorted(out, key=lambda e: e["created"])

    for tok, rec in list(_mem_tokens.items()):
        if rec.get("state") != "pending":
            continue
        if now - rec["created"] > int(_POLICY["approval_ttl"]):
            _mem_tokens.pop(tok, None)
            continue
        out.append({
            "token": tok,
            "actor": rec.get("actor"),
            "capability": rec.get("capability"),
            "summary": _redacted_summary(rec),
            "created": rec.get("created"),
            "expires": rec["created"] + int(_POLICY["approval_ttl"]),
        })
    return sorted(out, key=lambda e: e["created"])


def _read_token(tok: str) -> dict[str, Any] | None:
    r = _get_redis()
    if r is not None:
        import json as _j

        raw = r.get(_tok_key(tok))
        return _j.loads(raw) if raw else None
    rec = _mem_tokens.get(tok)
    if rec and time.time() - rec["created"] > int(_POLICY["approval_ttl"]):
        _mem_tokens.pop(tok, None)
        return None
    return rec


def _write_token(tok: str, rec: dict[str, Any]) -> None:
    r = _get_redis()
    if r is not None:
        import json as _j

        ttl = max(1, int(_POLICY["approval_ttl"] - (time.time() - rec["created"])))
        r.set(_tok_key(tok), _j.dumps(rec), ex=ttl)
    else:
        _mem_tokens[tok] = rec


# ── checks ───────────────────────────────────────────────────────────────────
def _granted_caps(actor: str) -> set[str]:
    return set(_POLICY["grants"].get(actor, []))


def has_grant(actor: str, capability: str) -> bool:
    caps = _granted_caps(actor)
    return "*" in caps or capability in caps


def requires_approval(capability: str, actor: str | None = None) -> bool:
    if capability not in set(_POLICY["requires_approval"]):
        return False
    if actor is not None:
        exempt = set(_POLICY.get("approval_exempt", {}).get(actor, []))
        if capability in exempt:
            return False
    return True


def allowed(actor: str, capability: str, *, approval: str | None = None) -> bool:
    try:
        require(actor, capability, approval=approval)
        return True
    except Denied:
        return False


def require(actor: str, capability: str, *, approval: str | None = None) -> None:
    """Assert ``actor`` may exercise ``capability`` now. Raises ``Denied``.

    Static grant is necessary but not sufficient for a ``requires_approval``
    capability — a matching, granted approval token must also be supplied.
    """
    try:
        actor = str(AgentId(actor))
    except ValueError as exc:
        raise Denied(str(actor), capability, f"invalid actor ({exc})") from None

    if not has_grant(actor, capability):
        raise Denied(actor, capability, "no static grant")

    if requires_approval(capability, actor):
        if not approval:
            raise Denied(actor, capability, "approval required but none supplied")
        rec = _read_token(approval)
        if not rec:
            raise Denied(actor, capability, "approval token unknown or expired")
        if rec.get("state") != "granted":
            raise Denied(actor, capability, f"approval not granted (state={rec.get('state')})")
        if rec.get("actor") != actor or rec.get("capability") != capability:
            raise Denied(actor, capability, "approval token does not match this request")


# ── fail-closed admin check ──────────────────────────────────────────────────
def admin_ids(env_var: str = "ADMIN_IDS") -> set[str]:
    raw = os.getenv(env_var, "") or ""
    return {p.strip() for p in raw.replace(";", ",").split(",") if p.strip()}


def is_admin(user_id: str | int, *, env_var: str = "ADMIN_IDS") -> bool:
    """Fail-closed: no configured admins ⇒ nobody is admin."""
    ids = admin_ids(env_var)
    return bool(ids) and str(user_id) in ids
