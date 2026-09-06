"""humanize — strip the well-known AI tells from finished text.

Deterministic and conservative. It only *removes or lightly rewrites* stock
phrasing; it never adds claims. Every number and proper noun in the input must
survive — if the rewrite would drop one, the original is returned unchanged.
Any exception also returns the original: a cosmetic pass must never be able to
drop or mangle a message.
"""
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger("swarm_core.refine.humanize")

# Trailing sign-offs / filler openers to drop (whole line, case-insensitive).
_SIGNOFF_RE = re.compile(
    r"(?im)^\s*(?:"
    r"i hope this helps[.!]?|"
    r"hope this helps[.!]?|"
    r"let me know if (?:you have any questions|there's anything else|you need anything else)[.!]?|"
    r"feel free to (?:ask|reach out)[^.\n]*[.!]?|"
    r"in (?:conclusion|summary)[,:]?|"
    r"at the end of the day[,:]?|"
    r"it'?s (?:important|worth) (?:to note|noting) that\s*"
    r")\s*$"
)

# Same, but as a trailing sentence at the very end of the text (not its own line).
_TRAILING_SIGNOFF_RE = re.compile(
    r"(?i)(?:\s+|^)(?:"
    r"i hope this helps|hope this helps|"
    r"let me know if (?:you have any questions|there'?s anything else|you need anything else)|"
    r"feel free to (?:ask|reach out)[^.!?\n]*"
    r")[.!]*\s*$"
)

# Sentence-initial / function words: capitalised but not proper nouns. Excluded
# from the proper-noun preservation guard so real names (Qdrant, Groq, ...) stay
# protected while "It" / "The" being dropped by a rewrite is fine.
_STARTER_WORDS = {
    "I", "It", "The", "This", "That", "These", "Those", "A", "An", "In", "On",
    "At", "We", "You", "If", "But", "And", "So", "Or", "As", "To", "Of", "For",
    "Its", "There", "Here", "They", "He", "She", "Their", "Our", "My", "Your",
    "When", "While", "Then", "Also", "Now", "Note",
}

# "It's not just X, it's Y" / "not only X but also Y" -> keep Y.
_NOT_JUST_RE = re.compile(
    r"(?i)\b(?:it'?s|this is|that'?s)\s+not\s+just\s+[^,.;]+,\s*(?:it'?s|it is)\s+",
)
_NOT_ONLY_RE = re.compile(r"(?i)\bnot\s+only\s+([^,.;]+?)\s+but\s+(?:also\s+)?")

# Inflated adjectives/adverbs -> plainer or nothing.
_INFLATION = {
    r"\bvery\s+unique\b": "unique",
    r"\babsolutely\s+essential\b": "essential",
    r"\bcompletely\s+revolutionary\b": "new",
    r"\bgame[- ]chang(?:er|ing)\b": "significant",
    r"\bcutting[- ]edge\b": "current",
    r"\bseamless(?:ly)?\b": "",
    r"\brobust(?:ly)?\b": "",
    r"\bleverage\b": "use",
    r"\bdelve into\b": "examine",
    r"\bin today'?s (?:fast[- ]paced )?world\b": "",
}

_WS_RE = re.compile(r"[ \t]{2,}")
_MULTINL_RE = re.compile(r"\n{3,}")

# For the fact-preservation guard.
_NUM_RE = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?%?")
_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]+(?:[A-Z][a-zA-Z0-9]+)*\b")


def _tokens(text: str) -> tuple[set[str], set[str]]:
    nums = {m.group(0).rstrip(".,") for m in _NUM_RE.finditer(text)}
    propers = {m.group(0) for m in _PROPER_RE.finditer(text)}
    return nums, propers


def _apply(text: str, voice: str | None) -> str:
    out = text
    out = _SIGNOFF_RE.sub("", out)
    out = _TRAILING_SIGNOFF_RE.sub("", out)
    out = _NOT_JUST_RE.sub("", out)
    out = _NOT_ONLY_RE.sub(r"\1 and ", out)
    for pat, repl in _INFLATION.items():
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    out = _WS_RE.sub(" ", out)
    out = _MULTINL_RE.sub("\n\n", out)
    # tidy spaces left before punctuation by the removals
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"(?m)^[ \t]+$", "", out)
    return out.strip()


def humanize(text: str, *, voice: str | None = None) -> str:
    """Return ``text`` with AI tells removed, or ``text`` unchanged on any
    failure or if a number / proper noun would be lost."""
    if not text or not isinstance(text, str):
        return text
    try:
        rewritten = _apply(text, voice)
        if not rewritten.strip():
            return text
        in_nums, in_propers = _tokens(text)
        out_nums, out_propers = _tokens(rewritten)
        if not in_nums.issubset(out_nums):
            log.info("humanize: numbers would change — keeping original")
            return text
        # proper nouns: ignore sentence-starter / function words (capitalised but
        # not names) — losing "It"/"The" to a rewrite is fine; losing "Qdrant" isn't.
        lost = (in_propers - out_propers) - _STARTER_WORDS
        if lost:
            log.info("humanize: proper nouns %s would be lost — keeping original", lost)
            return text
        return rewritten
    except Exception as e:  # noqa: BLE001
        log.warning("humanize failed (%s) — returning original", e)
        return text


def maybe_humanize(text: str, *, voice: str | None = None) -> str:
    """Env-gated (``SWARM_HUMANIZE``, default off). When on, humanize and then
    run ``leakscan`` — a rewrite is a new place for a redacted secret to
    reappear. If the scan trips, return the *original* untouched text."""
    if os.getenv("SWARM_HUMANIZE", "false").lower() != "true":
        return text
    rewritten = humanize(text, voice=voice)
    try:
        from swarm_core.security import leakscan
        if leakscan.scan(rewritten):
            log.warning("humanize: leakscan tripped on rewrite — returning original")
            return text
    except Exception:  # noqa: BLE001
        pass
    return rewritten
