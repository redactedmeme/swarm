"""Leak detection (IronClaw control 4).

Scan any text — an outbound HTTP body, an LLM response, tool output about to be
spliced into a prompt, an agent's chat reply — for material that looks like an
exfiltrated secret. IronClaw scans *both* request and response traffic; so do we,
at every chokepoint (``apps/swarm-egress``, ``apps/proxy``, the tool-output path,
the bot send path).

Design notes
------------
* Patterns are provider-shaped prefixes + structural shapes (PEM blocks, long
  hex, BIP-39 mnemonics), matching IronClaw's "15+ secret patterns" approach.
* ``scan`` never raises and is cheap enough to run on every message.
* Three severities map to three caller actions: ``block`` (refuse the
  request/response), ``redact`` (forward with the secret masked), ``warn``
  (forward, but audit it).
* A short allowlist prevents the obvious false positives (example keys in docs,
  the literal string ``sk-...``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal

Severity = Literal["block", "redact", "warn"]


@dataclass(frozen=True)
class _Rule:
    name: str
    pattern: re.Pattern[str]
    severity: Severity


@dataclass(frozen=True)
class LeakMatch:
    rule: str
    severity: Severity
    span: tuple[int, int]
    preview: str  # already masked — safe to log


# ── Rules ────────────────────────────────────────────────────────────────────
# Ordered most-specific first. `block` = credential material that must never
# leave; `redact` = high-signal but occasionally legitimate to echo; `warn` =
# structural guess.

_RULES: tuple[_Rule, ...] = (
    _Rule("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"), "block"),
    _Rule("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"), "block"),
    _Rule("xai_key", re.compile(r"\bxai-[A-Za-z0-9]{20,}"), "block"),
    _Rule("groq_key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "block"),
    _Rule("openrouter_key", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}"), "block"),
    _Rule("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"), "block"),
    _Rule("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "block"),
    _Rule("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "block"),
    _Rule("google_api_key", re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"), "block"),
    _Rule("telegram_bot_token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "block"),
    _Rule(
        "pem_private_key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
        "block",
    ),
    _Rule(
        "bip39_mnemonic",
        re.compile(r"\b(?:[a-z]{3,8}\s+){11,23}[a-z]{3,8}\b"),
        "block",
    ),
    _Rule(
        "solana_secret_array",
        re.compile(r"\[\s*(?:\d{1,3}\s*,\s*){63,}\d{1,3}\s*\]"),
        "block",
    ),
    _Rule(
        "db_connection_string",
        re.compile(r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|rediss)://[^\s/@]+:[^\s/@]+@"),
        "redact",
    ),
    _Rule("bearer_header", re.compile(r"[Aa]uthorization:\s*Bearer\s+[A-Za-z0-9._-]{20,}"), "redact"),
    _Rule("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "redact"),
    _Rule("hex_secret_64", re.compile(r"\b[0-9a-fA-F]{64}\b"), "warn"),
    _Rule("hex_secret_128", re.compile(r"\b[0-9a-fA-F]{128}\b"), "warn"),
)

# Literal fragments that make a match a false positive regardless of rule.
_ALLOW = re.compile(
    r"(?i)(?:example|placeholder|redacted|your[-_]?key|xxxx+|0{16,}|f{16,}|\bdummy\b|<[a-z_]+>)"
)

_SEVERITY_RANK = {"warn": 0, "redact": 1, "block": 2}


def _mask(s: str) -> str:
    s = s.strip()
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}…{s[-2:]} ({len(s)} chars)"


def scan(text: str | None) -> list[LeakMatch]:
    """Return every secret-shaped match in ``text``. Never raises."""
    if not text:
        return []
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return []

    out: list[LeakMatch] = []
    for rule in _RULES:
        for m in rule.pattern.finditer(text):
            frag = m.group(0)
            window = text[max(0, m.start() - 24) : m.end() + 24]
            if _ALLOW.search(frag) or _ALLOW.search(window):
                continue
            out.append(LeakMatch(rule.name, rule.severity, m.span(), _mask(frag)))
    return out


def worst(matches: Iterable[LeakMatch]) -> Severity | None:
    sev = None
    rank = -1
    for m in matches:
        if _SEVERITY_RANK[m.severity] > rank:
            rank, sev = _SEVERITY_RANK[m.severity], m.severity
    return sev


def redact(text: str | None, *, token: str = "‹redacted-secret›") -> tuple[str, list[LeakMatch]]:
    """Return ``(clean_text, matches)`` with every match replaced by ``token``.

    Overlapping/nested matches are handled by replacing right-to-left.
    """
    if not text:
        return text or "", []
    matches = scan(text)
    if not matches:
        return text, []
    spans = sorted({m.span for m in matches}, key=lambda s: s[0], reverse=True)
    out = text
    for start, end in spans:
        out = out[:start] + token + out[end:]
    return out, matches
