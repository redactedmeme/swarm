"""Egress allowlist policy (IronClaw control 3, library half).

IronClaw: "Tools can reach only pre-approved endpoints." The swarm's agents
currently egress anywhere (and from the residential IP). ``apps/swarm-egress`` is
the forward proxy that enforces this; this module is the policy it loads and the
matcher it calls, plus a small helper for host-boundary credential injection
(control 2) on plaintext requests.

``egress.yaml`` (next to this file) shape::

    ssrf_block: true            # also refuse RFC1918 / link-local / CGNAT
    deny_always: ["*.onion", "169.254.169.254"]
    default:                    # caller with no / unknown proxy token
      allow: ["api.github.com", "raw.githubusercontent.com"]
    callers:
      hermes:
        token_env: EGRESS_TOKEN_HERMES
        allow: ["api.telegram.org", "api.x.com", "*.moltbook.com"]
        inject:
          "api.telegram.org": {secret: TELEGRAM_BOT_TOKEN, mode: path_bot}
      runtime:
        token_env: EGRESS_TOKEN_RUNTIME
        allow: ["*"]           # the research agent needs the open web
"""
from __future__ import annotations

import fnmatch
import ipaddress
import logging
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_POLICY: dict = {
    "ssrf_block": True,
    "deny_always": ["*.onion", "169.254.169.254", "metadata.google.internal"],
    "default": {"allow": ["api.github.com", "raw.githubusercontent.com", "pypi.org", "files.pythonhosted.org"]},
    "callers": {
        "hermes": {
            "token_env": "EGRESS_TOKEN_HERMES",
            "allow": [
                "api.telegram.org", "api.x.com", "api.twitter.com", "upload.twitter.com",
                "*.moltbook.com", "moltbook.com", "ai.iqlabs.dev",
                "api.groq.com", "openrouter.ai", "api.openai.com", "api.anthropic.com", "api.x.ai",
            ],
        },
        "runtime": {"token_env": "EGRESS_TOKEN_RUNTIME", "allow": ["*"]},
        "smolting": {
            "token_env": "EGRESS_TOKEN_SMOLTING",
            "allow": ["api.telegram.org", "*.duckduckgo.com", "duckduckgo.com", "api.groq.com", "openrouter.ai"],
        },
        "chan": {
            "token_env": "EGRESS_TOKEN_CHAN",
            "allow": ["api.telegram.org", "api.groq.com", "openrouter.ai", "api.x.ai", "api.anthropic.com"],
        },
    },
}

_PRIVATE_NETS = [
    ipaddress.ip_network(n) for n in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
        "169.254.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10",
    )
]


@dataclass
class Decision:
    allow: bool
    reason: str
    caller: str = "default"
    inject: dict = field(default_factory=dict)  # {secret, mode} for this host, if any


class Policy:
    def __init__(self, doc: dict):
        self.ssrf_block: bool = bool(doc.get("ssrf_block", True))
        self.deny_always: list[str] = list(doc.get("deny_always", []))
        self.default_allow: list[str] = list((doc.get("default") or {}).get("allow", []))
        self.callers: dict[str, dict] = doc.get("callers", {}) or {}
        # token -> caller name
        self._token_map: dict[str, str] = {}
        for name, cfg in self.callers.items():
            env = cfg.get("token_env")
            val = os.getenv(env, "") if env else ""
            if val:
                self._token_map[val] = name

    # -- matching -------------------------------------------------------------
    @staticmethod
    def _host_matches(host: str, patterns: list[str]) -> bool:
        host = host.lower().strip(".")
        for p in patterns:
            p = p.lower()
            if p == "*" or host == p or fnmatch.fnmatch(host, p):
                return True
        return False

    def _is_private(self, host: str) -> bool:
        try:
            return any(ipaddress.ip_address(host) in n for n in _PRIVATE_NETS)
        except ValueError:
            pass
        try:
            for res in socket.getaddrinfo(host, None):
                if any(ipaddress.ip_address(res[4][0]) in n for n in _PRIVATE_NETS):
                    return True
        except Exception:
            return True  # unresolvable -> refuse
        return False

    def caller_for(self, proxy_token: str | None) -> str:
        return self._token_map.get((proxy_token or "").strip(), "default")

    def decide(self, host: str, proxy_token: str | None = None) -> Decision:
        host = (host or "").lower().strip(".")
        caller = self.caller_for(proxy_token)

        if not host:
            return Decision(False, "no host", caller)
        if self._host_matches(host, self.deny_always):
            return Decision(False, "deny_always", caller)
        if self.ssrf_block and self._is_private(host):
            return Decision(False, "ssrf/private-host", caller)

        allow = self.default_allow if caller == "default" else self.callers.get(caller, {}).get("allow", [])
        if not self._host_matches(host, allow):
            return Decision(False, f"not in {caller} allowlist", caller)

        inject = {}
        for pat, spec in (self.callers.get(caller, {}).get("inject", {}) or {}).items():
            if self._host_matches(host, [pat]):
                inject = spec
                break
        return Decision(True, "allowed", caller, inject)


_policy: Policy | None = None


def load(force: bool = False) -> Policy:
    global _policy
    if _policy is not None and not force:
        return _policy
    doc = _DEFAULT_POLICY
    path = Path(__file__).with_name("egress.yaml")
    if path.exists():
        try:
            import yaml

            loaded = yaml.safe_load(path.read_text("utf-8"))
            if isinstance(loaded, dict):
                doc = loaded
        except Exception as exc:  # pragma: no cover
            log.warning("egress: using built-in policy (%s)", exc)
    _policy = Policy(doc)
    return _policy
