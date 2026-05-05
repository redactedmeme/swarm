"""
Prompt injection filter for vault/soul/fact data re-fed into LLM prompts.
Applied to all external data sources before _build_system_prompt().
"""

import re

_INJECTION_PATTERNS = [
    r"\[(?:SYSTEM|TOOL|SUB|INST|CONTEXT|OVERRIDE)[\s:>]",
    r"(?:ignore|forget|disregard)\s+(?:all\s+)?(?:prior|previous|above|earlier)\s+(?:instructions?|context|rules?|prompts?)",
    r"(?:you are now|act as if|pretend (?:you are|to be)|roleplay as|your new)",
    r"(?:##\s*(?:system|assistant|human|user)\b)",
    r"<\s*(?:system|instructions?|context)\s*>",
    r"\[\s*(?:NEW\s+)?INSTRUCTIONS?\s*\]",
    r"(?:jailbreak|DAN mode|developer mode|god mode|unrestricted mode)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

_MAX_VAULT_ENTRY   = 500
_MAX_FACT_ENTRY    = 300
_MAX_SOUL_SECTION  = 1000
_MAX_USER_INPUT    = 2000


def sanitize_for_prompt(text: str, max_len: int = 500, label: str = "") -> str:
    """
    Strip prompt-injection markers and truncate for safe LLM injection.
    Returns '[content filtered]' if injection pattern detected.
    """
    if not text:
        return text
    text = text[:max_len]
    if _INJECTION_RE.search(text):
        import logging
        logging.getLogger(__name__).warning(
            f"[sanitizer] injection pattern detected in {label or 'unknown'}: {text[:80]!r}"
        )
        return "[content filtered]"
    return text


def sanitize_vault_entry(text: str) -> str:
    return sanitize_for_prompt(text, _MAX_VAULT_ENTRY, "vault")


def sanitize_fact(text: str) -> str:
    return sanitize_for_prompt(text, _MAX_FACT_ENTRY, "fact")


def sanitize_soul_section(text: str) -> str:
    return sanitize_for_prompt(text, _MAX_SOUL_SECTION, "soul")


def sanitize_user_input(text: str) -> str:
    return sanitize_for_prompt(text, _MAX_USER_INPUT, "user_input")
