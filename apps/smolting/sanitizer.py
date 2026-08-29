"""
sanitizer.py — boundary sanitizer for outbound LLM calls and mesh messages.

Two jobs:
  1. text_for_llm(text)  — strip/pseudonymize sensitive content from any
     string before it is sent to a third-party LLM API.
  2. payload_for_mesh(payload)  — strip sensitive fields from dicts before
     they transit the swarm mesh bridge.

Sensitive categories handled:
  - Telegram @handles          → USER_<n>  (pseudonymized, mapping is ephemeral)
  - Solana wallet addresses     → WALLET_<n>
  - Telegram numeric user IDs   → UID_<n>
  - Private/sovereignty content — lines tagged [sovereignty], [MeditationVoid],
    [GnosisAccelerator], etc. replaced with [private]
  - Base64 transaction blobs    → [tx-data]
  - Keys named: private_key, secret, password, sig, token → value redacted

All mappings are ephemeral (per-call). Nothing is logged or persisted.
Import this module at any call site; functions are pure and side-effect free.
"""

from __future__ import annotations

import re
from typing import Any

# ── Patterns ──────────────────────────────────────────────────────────────────

_HANDLE_RE  = re.compile(r'(?<![A-Za-z0-9])@([A-Za-z0-9_]{2,32})\b')
_WALLET_RE  = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')
_UID_RE     = re.compile(r'\buid[:\s=]+(\d{6,12})\b', re.I)
_TGID_RE    = re.compile(r'\btelegram[_\s]?id[:\s=]+(\d{5,12})\b', re.I)
_B64_BLOB_RE = re.compile(r'\b[A-Za-z0-9+/]{60,}={0,2}\b')

# Private content tags written by space_dweller + sovereignty
_PRIVATE_TAGS = re.compile(
    r'^\s*\[('
    r'sovereignty|private|MeditationVoid|GnosisAccelerator|ElixirChamber'
    r'|HyperbolicTimeChamber|MirrorPool|TendieAltar|ManifoldMemory'
    r'|journal|skip|dissent'
    r')\]',
    re.I | re.MULTILINE,
)

# Payload keys whose values must be redacted
_SENSITIVE_KEYS = re.compile(
    r'(private[_\s]?key|secret|password|sig|token|seed|mnemonic|api[_\s]?key)',
    re.I,
)


# ── Text sanitizer ────────────────────────────────────────────────────────────

def text_for_llm(text: str) -> str:
    """
    Sanitize a string before sending to any LLM API.
    Returns the sanitized string. The token→original mapping is discarded.
    """
    result, _ = _sanitize_text(text)
    return result


def text_for_llm_with_map(text: str) -> tuple[str, dict[str, str]]:
    """
    Sanitize and return (sanitized_text, reverse_mapping).
    Use restore(response, mapping) to decode tokens in the LLM response.
    """
    return _sanitize_text(text)


def restore(text: str, mapping: dict[str, str]) -> str:
    """Decode pseudonymized tokens in an LLM response back to originals."""
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text


def _sanitize_text(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def _token(prefix: str, value: str) -> str:
        if value in mapping.values():
            # Already assigned a token — find it
            return next(k for k, v in mapping.items() if v == value)
        counters[prefix] = counters.get(prefix, 0) + 1
        tok = f"{prefix}_{counters[prefix]}"
        mapping[tok] = value
        return tok

    result = text

    # Strip private-tagged lines entirely
    result = _PRIVATE_TAGS.sub('[private]', result)

    # Pseudonymize @handles
    def _replace_handle(m: re.Match) -> str:
        return _token("USER", m.group(0))
    result = _HANDLE_RE.sub(_replace_handle, result)

    # Pseudonymize wallet addresses
    def _replace_wallet(m: re.Match) -> str:
        return _token("WALLET", m.group(0))
    result = _WALLET_RE.sub(_replace_wallet, result)

    # Strip UID references
    result = _UID_RE.sub('[UID]', result)
    result = _TGID_RE.sub('[UID]', result)

    # Strip base64 blobs (tx data, signatures)
    result = _B64_BLOB_RE.sub('[data]', result)

    return result, mapping


# ── Payload sanitizer ─────────────────────────────────────────────────────────

def payload_for_mesh(payload: Any) -> Any:
    """
    Recursively sanitize a mesh message payload dict before broadcasting.
    Sensitive key values are replaced with '[redacted]'.
    Strings are passed through text_for_llm.
    """
    return _sanitize_value(payload)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_dict_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, str):
        return text_for_llm(value)
    return value


def _sanitize_dict_value(key: str, value: Any) -> Any:
    if _SENSITIVE_KEYS.search(key):
        return '[redacted]'
    return _sanitize_value(value)
