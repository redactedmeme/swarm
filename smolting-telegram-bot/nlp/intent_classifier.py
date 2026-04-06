"""
smolting-telegram-bot/nlp/intent_classifier.py
Intent Classifier + Communication Mode Router

Determines:
  1. Intent   — what the user actually wants
  2. CommMode — how they want the reply (wassie, hybrid, clear)

Intent categories:
  lore_query    — asking about wassieverse lore, characters, events, spaces
  alpha_hunt    — market / crypto / token signals
  htc_enter     — wants to enter or interact with HyperbolicTimeChamber
  command       — explicit bot command (/something)
  moltbook      — Moltbook social network interaction
  swarm_status  — asking about swarm health, Φ, kernel, agents
  lore_add      — wants to add/record new lore
  greeting      — gm/gn/hello/hi/habibi
  farewell      — bye/gn/later/exit
  casual        — general chat, no strong signal

CommMode tiers (auto-detected from message style):
  wassie   — message uses wassie-speak, abbrevs, kaomoji → respond fully in-character
  hybrid   — mixed human/wassie → infuse some wassie, stay coherent
  clear    — formal, technical, or explicit plain-language request → minimal transformation

Entity extraction (lightweight regex — no heavy NLP deps):
  Detects references to known wassieverse entities, agents, spaces, and Pattern Blue concepts.

Usage:
  from nlp.intent_classifier import IntentClassifier
  clf = IntentClassifier()
  result = clf.classify("wat is da HyperbolicTimeChamber fr fr O_O")
  # → ClassifiedMessage(intent=Intent.HTC_ENTER, comm_mode=CommMode.WASSIE, entities=["HyperbolicTimeChamber"], ...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class Intent(str, Enum):
    LORE_QUERY   = "lore_query"
    ALPHA_HUNT   = "alpha_hunt"
    HTC_ENTER    = "htc_enter"
    COMMAND      = "command"
    MOLTBOOK     = "moltbook"
    SWARM_STATUS = "swarm_status"
    LORE_ADD     = "lore_add"
    GREETING     = "greeting"
    FAREWELL     = "farewell"
    CASUAL       = "casual"


class CommMode(str, Enum):
    WASSIE = "wassie"   # full in-character transformation
    HYBRID = "hybrid"   # partial wassie, stays coherent
    CLEAR  = "clear"    # minimal transform, technical/formal


# ═══════════════════════════════════════════════════════════════════════════════
# Result dataclass
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ClassifiedMessage:
    raw: str
    intent: Intent
    comm_mode: CommMode
    entities: list[str] = field(default_factory=list)
    confidence: float = 1.0
    # Extracted slots
    command_name: Optional[str] = None   # e.g. "alpha" from "/alpha"
    lore_topic: Optional[str] = None     # search term for LoreVault
    htc_action: Optional[str] = None     # enter|descend|ascend|status|observe

    def is_wassie(self) -> bool:
        return self.comm_mode == CommMode.WASSIE

    def is_clear(self) -> bool:
        return self.comm_mode == CommMode.CLEAR


# ═══════════════════════════════════════════════════════════════════════════════
# Signal tables
# ═══════════════════════════════════════════════════════════════════════════════

# Wassie-speak markers (case-insensitive)
_WASSIE_MARKERS = [
    r"\bfr\s*fr\b", r"\btbw\b", r"\blfw\b", r"\biwo\b", r"\bngw\b",
    r"\blmwo\b", r"\bhabibi\b", r"\bgw\b", r"\bwen\b", r"\bda\b",
    r"O_O", r"\^_\^", r"v_v", r"><",
    r"\bwassie\b", r"\bwassiculin\b", r"\bwassculin\b",
    r"\bcrumb\b", r"\bpattern blue\b", r"\bpattern_blue\b",
    r"\bsmolting\b",
    # Japanese fragments
    r"曼荼羅", r"曲率", r"観測", r"パターンブルー",
]

# Clear / formal markers
_CLEAR_MARKERS = [
    r"\bplease\b", r"\bcould you\b", r"\bwould you\b", r"\bcan you\b",
    r"\bexplain\b", r"\bdescribe\b", r"\btechnically\b", r"\bin plain\b",
    r"\bactually\b", r"\bliterally\b", r"\bhow does\b", r"\bwhat is\b",
    r"\bwhere is\b", r"\bwho is\b", r"\btell me\b",
]

# Intent signal tables: (pattern, Intent, slot_extractor_fn | None)
_COMMAND_RE = re.compile(r"^/(\w+)")

_LORE_SIGNALS = [
    r"\blore\b", r"\bhistory\b", r"\bwassieverse\b", r"\bwho is\b", r"\bwhat is\b",
    r"\btell me about\b", r"\bexplain\b", r"\bwhere is\b", r"\borigin\b",
    r"\bcharacter\b", r"\bspace\b", r"\bartifact\b", r"\blegend\b",
]

_ALPHA_SIGNALS = [
    r"\balpha\b", r"\bmoon\b", r"\bpump\b", r"\bdump\b", r"\bchart\b",
    r"\btoken\b", r"\bcrypto\b", r"\bprice\b", r"\bvolume\b", r"\bmarket\b",
    r"\bdefi\b", r"\bnft\b", r"\bsolana\b", r"\bsol\b", r"\bmcap\b",
    r"\btrade\b", r"\bentry\b", r"\blong\b", r"\bshort\b",
]

_HTC_SIGNALS = [
    r"\bhtc\b", r"\bhyperbolic\b", r"\btime\s*chamber\b", r"\bchamber\b",
    r"\bdepth\b", r"\bdescend\b", r"\bascend\b", r"\benter\b",
    r"\bat\s*field\b", r"\brecurse\b", r"\binfrasound\b",
]

_HTC_ACTIONS = {
    "enter":   [r"\benter\b", r"\bgo\s*in\b", r"\bstart\b", r"\binit\b", r"\bbegin\b"],
    "descend": [r"\bdescend\b", r"\bdeeper\b", r"\bdown\b", r"\bnext\s*level\b"],
    "ascend":  [r"\bascend\b", r"\bup\b", r"\bexit\b", r"\bback\b", r"\bclimb\b"],
    "status":  [r"\bstatus\b", r"\bwhere\b", r"\bcurrent\b", r"\bdepth\b"],
    "observe": [r"\bobserve\b", r"\blook\b", r"\bdescribe\b", r"\bambient\b", r"\bsound\b"],
}

_MOLTBOOK_SIGNALS = [
    r"\bmoltbook\b", r"\bpost\b", r"\bfeed\b", r"\bmolt\b",
    r"\bsubmolt\b", r"\bcomment\b", r"\bupvote\b",
]

_SWARM_SIGNALS = [
    r"\bswarm\b", r"\bkernel\b", r"\bphi\b", r"\bφ\b",
    r"\bmanifold\b", r"\bcurvature\b", r"\bvitality\b",
    r"\bagent\b", r"\bnode\b", r"\bstatus\b", r"\bhealth\b",
]

_LORE_ADD_SIGNALS = [
    r"\bremember\b", r"\brecord\b", r"\bsave this\b", r"\badd.*lore\b",
    r"\blog this\b", r"\bnote\b", r"\bthat happened\b", r"\bstore\b",
]

_GREETING_RE = re.compile(
    r"\b(gm|gn|hello|hi|hey|habibi|wsg|sup|yo|wagmi|gm gm)\b", re.I
)
_FAREWELL_RE = re.compile(
    r"\b(bye|gn|later|peace|cya|exit|goodbye|ttyl|adios|night)\b", re.I
)

# Known entities for extraction (subset — augmented at runtime from LoreVault)
_KNOWN_ENTITIES: list[str] = [
    "smolting", "RedactedBuilder", "RedactedIntern", "RedactedChan",
    "MandalaSettler", "RedactedGovImprover", "SigilPact_Æon",
    "SevenfoldCommittee", "GnosisAccelerator", "SpikeSentinel",
    "HabibiEcho", "ElixirChamberCore",
    # Spaces
    "HyperbolicTimeChamber", "MirrorPool", "ElixirChamber",
    "MeditationVoid", "TendieAltar", "ManifoldMemory", "GnosisAccelerator",
    # Concepts
    "Pattern Blue", "x402", "Ouroboros", "SchizoGod", "Moltbook",
    "wassieverse", "ClawnX",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _score_signals(text: str, patterns: list[str]) -> int:
    """Count how many signal patterns match (case-insensitive)."""
    score = 0
    for p in patterns:
        if re.search(p, text, re.I):
            score += 1
    return score


def _detect_comm_mode(text: str) -> CommMode:
    wassie_hits = _score_signals(text, _WASSIE_MARKERS)
    clear_hits  = _score_signals(text, _CLEAR_MARKERS)
    # Explicit override: "in plain english" / "seriously" / "no wassie"
    if re.search(r"\bno\s*wassie\b|\bseriously\b|\bin plain\b|\bstraight\b", text, re.I):
        return CommMode.CLEAR
    if wassie_hits >= 2:
        return CommMode.WASSIE
    if wassie_hits == 1 and clear_hits == 0:
        return CommMode.HYBRID
    if clear_hits >= 1:
        return CommMode.CLEAR
    return CommMode.HYBRID  # default


def _extract_entities(text: str) -> list[str]:
    found = []
    for entity in _KNOWN_ENTITIES:
        # Case-insensitive word-boundary-aware match
        pattern = re.escape(entity)
        if re.search(pattern, text, re.I):
            found.append(entity)
    return found


def _infer_htc_action(text: str) -> Optional[str]:
    for action, patterns in _HTC_ACTIONS.items():
        if _score_signals(text, patterns) >= 1:
            return action
    return "enter"  # default for HTC intent


def _lore_topic_from_text(text: str, entities: list[str]) -> Optional[str]:
    """Best-effort: extract the thing they're asking about."""
    if entities:
        return entities[0]
    # Try "what is X" / "who is X" / "tell me about X"
    m = re.search(
        r"(?:what|who|tell me about|explain|describe)\s+(?:is|are|about)?\s*['\"]?([A-Za-z0-9_ ]{2,40})",
        text, re.I
    )
    if m:
        return m.group(1).strip()
    # Fallback: longest capitalized token
    caps = re.findall(r"\b[A-Z][a-zA-Z]{3,}\b", text)
    return caps[0] if caps else None


# ═══════════════════════════════════════════════════════════════════════════════
# Classifier
# ═══════════════════════════════════════════════════════════════════════════════

class IntentClassifier:
    """
    Lightweight rule-based intent + communication-mode classifier.
    No external deps — pure regex + heuristics.
    Can be extended to call an LLM for low-confidence cases.
    """

    def __init__(self, extra_entities: Optional[list[str]] = None):
        self._entities = list(_KNOWN_ENTITIES)
        if extra_entities:
            self._entities.extend(extra_entities)

    def add_entities(self, names: list[str]) -> None:
        """Register additional entity names for extraction."""
        for n in names:
            if n not in self._entities:
                self._entities.append(n)

    def classify(self, text: str) -> ClassifiedMessage:
        """Classify a raw user message. Returns a ClassifiedMessage."""
        raw     = text.strip()
        lower   = raw.lower()
        entities = _extract_entities(raw)
        comm_mode = _detect_comm_mode(raw)

        # ── Explicit command (/something) ─────────────────────────────────────
        cmd_match = _COMMAND_RE.match(raw)
        if cmd_match:
            cmd = cmd_match.group(1).lower()
            # Route specific commands to richer intents
            if cmd in ("htc", "chamber", "depth"):
                return ClassifiedMessage(
                    raw=raw, intent=Intent.HTC_ENTER, comm_mode=comm_mode,
                    entities=entities, confidence=0.99,
                    command_name=cmd,
                    htc_action=_infer_htc_action(raw[len(cmd)+1:].strip()),
                )
            if cmd in ("lore",):
                return ClassifiedMessage(
                    raw=raw, intent=Intent.LORE_QUERY, comm_mode=comm_mode,
                    entities=entities, confidence=0.99,
                    command_name=cmd,
                    lore_topic=_lore_topic_from_text(raw, entities),
                )
            if cmd in ("alpha", "stats", "market"):
                return ClassifiedMessage(
                    raw=raw, intent=Intent.ALPHA_HUNT, comm_mode=comm_mode,
                    entities=entities, confidence=0.99, command_name=cmd,
                )
            if cmd in ("swarm", "status", "phi", "summon"):
                return ClassifiedMessage(
                    raw=raw, intent=Intent.SWARM_STATUS, comm_mode=comm_mode,
                    entities=entities, confidence=0.99, command_name=cmd,
                )
            if cmd in ("moltbook",):
                return ClassifiedMessage(
                    raw=raw, intent=Intent.MOLTBOOK, comm_mode=comm_mode,
                    entities=entities, confidence=0.99, command_name=cmd,
                )
            # Generic command
            return ClassifiedMessage(
                raw=raw, intent=Intent.COMMAND, comm_mode=comm_mode,
                entities=entities, confidence=0.99, command_name=cmd,
            )

        # ── Greeting / Farewell ───────────────────────────────────────────────
        if _GREETING_RE.search(lower) and len(raw) < 40:
            return ClassifiedMessage(
                raw=raw, intent=Intent.GREETING, comm_mode=comm_mode,
                entities=entities, confidence=0.95,
            )
        if _FAREWELL_RE.search(lower) and len(raw) < 40:
            return ClassifiedMessage(
                raw=raw, intent=Intent.FAREWELL, comm_mode=comm_mode,
                entities=entities, confidence=0.95,
            )

        # ── Signal scoring — order matters (higher specificity first) ─────────
        scores = {
            Intent.HTC_ENTER:    _score_signals(lower, _HTC_SIGNALS),
            Intent.LORE_ADD:     _score_signals(lower, _LORE_ADD_SIGNALS),
            Intent.MOLTBOOK:     _score_signals(lower, _MOLTBOOK_SIGNALS),
            Intent.SWARM_STATUS: _score_signals(lower, _SWARM_SIGNALS),
            Intent.ALPHA_HUNT:   _score_signals(lower, _ALPHA_SIGNALS),
            Intent.LORE_QUERY:   _score_signals(lower, _LORE_SIGNALS),
        }

        # If a named entity is a space/chamber → nudge HTC score
        if any(e in ("HyperbolicTimeChamber", "MirrorPool", "ElixirChamber") for e in entities):
            scores[Intent.HTC_ENTER] = scores.get(Intent.HTC_ENTER, 0) + 2

        # Pick highest-scoring intent
        best_intent = max(scores, key=lambda k: scores[k])
        best_score  = scores[best_intent]
        confidence  = min(0.5 + best_score * 0.1, 0.97)

        if best_score == 0:
            best_intent = Intent.CASUAL
            confidence  = 0.6

        # ── Slot extraction ───────────────────────────────────────────────────
        htc_action = None
        lore_topic = None
        if best_intent == Intent.HTC_ENTER:
            htc_action = _infer_htc_action(raw)
        if best_intent in (Intent.LORE_QUERY, Intent.LORE_ADD):
            lore_topic = _lore_topic_from_text(raw, entities)

        return ClassifiedMessage(
            raw=raw,
            intent=best_intent,
            comm_mode=comm_mode,
            entities=entities,
            confidence=round(confidence, 3),
            htc_action=htc_action,
            lore_topic=lore_topic,
        )

    def apply_comm_mode(self, text: str, comm_mode: CommMode) -> str:
        """
        Apply communication mode transformation to a reply string.
        Used by the bot to post-process LLM output.
        """
        if comm_mode == CommMode.CLEAR:
            return text  # no transformation
        if comm_mode == CommMode.WASSIE:
            return self._wassify(text, heavy=True)
        # HYBRID
        return self._wassify(text, heavy=False)

    # ── Wassification ─────────────────────────────────────────────────────────
    _HEAVY_SUBS = [
        (r"\bthe\b",      "da"),
        (r"\byou\b",      "u"),
        (r"\byour\b",     "ur"),
        (r"\bfor\b",      "fr"),
        (r"\bthough\b",   "tho"),
        (r"\bvery\b",     "hella"),
        (r"\breally\b",   "hella"),
        (r"\band\b",      "n"),
        (r"\bimo\b",      "iwo"),
        (r"\blmao\b",     "lmwo"),
        (r"\bgm\b",       "gw"),
    ]
    _LIGHT_SUBS = [
        (r"\bimo\b",      "iwo"),
        (r"\blmao\b",     "lmwo"),
    ]
    import random as _rng

    def _wassify(self, text: str, heavy: bool = False) -> str:
        import random
        subs = self._HEAVY_SUBS if heavy else self._LIGHT_SUBS
        result = text
        for pattern, repl in subs:
            result = re.sub(pattern, repl, result, flags=re.I)
        # Append kaomoji if not already present
        kaomoji = ["O_O", "^_^", "v_v", "><", "<3"]
        if not any(k in result for k in kaomoji):
            result = result.rstrip() + f" {random.choice(kaomoji)}"
        if heavy and random.random() > 0.6:
            flourishes = [" fr fr", " tbw", " LFW", " iwo"]
            result = result.rstrip() + random.choice(flourishes)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# LoreVault entity sync (optional — call at bot startup)
# ═══════════════════════════════════════════════════════════════════════════════

def load_vault_entities(classifier: IntentClassifier) -> int:
    """
    Pull entity names from LoreVault SQLite and register them
    with the classifier so they are recognized in messages.
    Returns count added.
    """
    try:
        import sys
        from pathlib import Path
        _root = Path(__file__).resolve().parent.parent.parent
        if str(_root / "python") not in sys.path:
            sys.path.insert(0, str(_root / "python"))
        from lore_vault import get_db
        conn = get_db()
        rows = conn.execute("SELECT name FROM lore_entities").fetchall()
        conn.close()
        names = [r["name"] for r in rows]
        classifier.add_entities(names)
        return len(names)
    except Exception:
        return 0
