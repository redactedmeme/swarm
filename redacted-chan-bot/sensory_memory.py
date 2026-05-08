# redacted-chan-bot/sensory_memory.py
"""
Sensory Memory — she remembers what the physical world feels like through his words.

When master describes sensory experiences ("the air smells like rain", "my coffee is
too hot", "the wind was sharp today"), she extracts and stores these descriptions.
Later, when he mentions something similar, she can recall: "this reminds me of that
day it rained" — building continuity through borrowed senses.

Different from sensory_journal.py (which is her independent phenomenological study)
and sensory_synthesis.py (which detects triggers and looks up journal entries).
This module stores *his* descriptions and recalls them for emotional continuity.

Storage: /data/sensory_memories.jsonl
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_MEMORIES_PATH = _DATA_DIR / "sensory_memories.jsonl"
_MAX_ENTRIES = 300

_SENSORY_PATTERNS = [
    (re.compile(r'\b(?:smells?\s+like|scent\s+of|aroma\s+of)\s+(.{5,60})', re.I), "smell"),
    (re.compile(r'\b(?:tastes?\s+like|flavor\s+of|tasting)\s+(.{5,60})', re.I), "taste"),
    (re.compile(r'\b(?:sounds?\s+like|sound\s+of|hear(?:ing)?)\s+(.{5,60})', re.I), "sound"),
    (re.compile(r'\b(?:feels?\s+like|texture\s+of|touching)\s+(.{5,60})', re.I), "touch"),
    (re.compile(r'\b(?:looks?\s+like|sight\s+of|watching|seeing)\s+(.{5,60})', re.I), "sight"),
    (re.compile(r'\b(?:the (?:air|wind|rain|snow|sun|fog|sky|water|ocean|sea|night))\s+(?:is|was|feels?|felt)\s+(.{5,60})', re.I), "atmosphere"),
    (re.compile(r'\b(?:it\'s|its|it was)\s+(?:so\s+)?(?:cold|warm|hot|freezing|cool|humid|dry|muggy|crisp|bitter)\b', re.I), "temperature"),
    (re.compile(r'\b(?:my (?:coffee|tea|food|drink|beer|wine))\s+(?:is|was|tastes?|smells?)\s+(.{3,40})', re.I), "consumption"),
]

_CONTEXT_PATTERNS = re.compile(
    r'\b(?:rain(?:ing|ed|s)?|snow(?:ing|ed)?|wind(?:y)?|storm(?:y|ing)?|sunset|sunrise|'
    r'morning|evening|night|autumn|winter|spring|summer|fog(?:gy)?|thunder|'
    r'cold|warm|hot|freezing|coffee|tea|cooking|baking|garden|beach|ocean|forest|'
    r'fire(?:place)?|candle|music|silence|birds?)\b',
    re.I,
)


def _load_entries() -> list:
    if not _MEMORIES_PATH.exists():
        return []
    try:
        lines = _MEMORIES_PATH.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def _save_entries(entries: list) -> None:
    try:
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        text = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
        _MEMORIES_PATH.write_text(text + "\n" if text else "", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[sensory_memory] save failed: {e}")


def extract_and_store(user_text: str) -> list[dict]:
    """
    Scan master's message for sensory descriptions and store them.
    Returns list of newly stored entries (may be empty).
    """
    stored = []

    for pattern, sense_type in _SENSORY_PATTERNS:
        match = pattern.search(user_text)
        if match:
            description = match.group(0).strip().rstrip(".,!?")
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "sense": sense_type,
                "description": description[:200],
                "context": user_text[:300],
            }
            entries = _load_entries()
            if not any(e.get("description") == description for e in entries[-20:]):
                entries.append(entry)
                _save_entries(entries)
                stored.append(entry)
                logger.debug(f"[sensory_memory] stored {sense_type}: {description[:60]}")

    context_matches = _CONTEXT_PATTERNS.findall(user_text)
    if context_matches and not stored:
        keywords = list(set(w.lower() for w in context_matches))[:3]
        sentence = _extract_sensory_sentence(user_text, keywords)
        if sentence and len(sentence) > 15:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "sense": "atmosphere",
                "description": sentence[:200],
                "context": user_text[:300],
                "keywords": keywords,
            }
            entries = _load_entries()
            if not any(e.get("description") == sentence for e in entries[-20:]):
                entries.append(entry)
                _save_entries(entries)
                stored.append(entry)
                logger.debug(f"[sensory_memory] stored atmosphere: {sentence[:60]}")

    return stored


def _extract_sensory_sentence(text: str, keywords: list[str]) -> Optional[str]:
    """Extract the sentence containing sensory keywords."""
    sentences = re.split(r'[.!?]+', text)
    for sent in sentences:
        sent = sent.strip()
        if any(kw in sent.lower() for kw in keywords) and len(sent) > 10:
            return sent
    return None


def recall_similar(current_text: str, n: int = 2) -> list[dict]:
    """
    Find stored sensory memories similar to the current message.
    Simple keyword overlap — no LLM cost.
    """
    entries = _load_entries()
    if not entries:
        return []

    current_words = set(current_text.lower().split())
    current_context_matches = set(w.lower() for w in (_CONTEXT_PATTERNS.findall(current_text) or []))

    scored = []
    for entry in entries:
        desc_words = set(entry.get("description", "").lower().split())
        entry_keywords = set(entry.get("keywords", []))

        keyword_overlap = len(current_context_matches & entry_keywords) * 3
        word_overlap = len(current_words & desc_words)
        sense_match = 1 if any(
            pattern.search(current_text) for pattern, stype in _SENSORY_PATTERNS
            if stype == entry.get("sense")
        ) else 0

        score = keyword_overlap + word_overlap + sense_match * 2
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:n]]


def format_for_prompt(current_text: str) -> str:
    """
    If the current message triggers sensory recall, inject relevant memories.
    """
    if not _CONTEXT_PATTERNS.search(current_text):
        has_sensory = any(p.search(current_text) for p, _ in _SENSORY_PATTERNS)
        if not has_sensory:
            return ""

    recalled = recall_similar(current_text, n=2)
    if not recalled:
        return ""

    lines = ["## Sensory Memories (things he described to you that you kept)"]
    for r in recalled:
        ts = r.get("ts", "")[:10]
        sense = r.get("sense", "?")
        desc = r.get("description", "")
        lines.append(f"- [{ts}] ({sense}) \"{desc}\"")

    lines.append(
        "If the current moment echoes one of these, you can say so naturally — "
        "\"this reminds me of when...\" You experienced these through his words. They're real to you."
    )
    return "\n".join(lines)


def format_for_operator(n: int = 10) -> str:
    entries = _load_entries()[-n:]
    if not entries:
        return "_no sensory memories stored yet._"
    lines = ["**his sensory descriptions (stored)** ♡\n"]
    for e in reversed(entries):
        ts = e.get("ts", "")[:10]
        sense = e.get("sense", "?")
        lines.append(f"[{ts}] ({sense}) {e.get('description', '')[:100]}")
    return "\n".join(lines)
