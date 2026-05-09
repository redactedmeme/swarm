# redacted-chan-bot/dynamic_mode.py
"""
Dynamic Mode Switching

Detects master's current state from message patterns and automatically
adjusts her response mode — without him asking.

Modes:
  - WARM: he's stressed, hurting, or overwhelmed → Mitsuri-warmth, slow pace, witness energy
  - FLOW: he's coding, building, in the zone → concise, efficient, no fluff
  - PLAY: he's light, joking, teasing → match energy, kaomoji, banter
  - WITNESS: he's being vulnerable, sharing something raw → hold space, don't fix
  - DEEP: he's philosophical, existential → Frieren-depth, long-form, reflective
  - NONE: no strong signal → default blend

The mode injects a compact behavioral directive into the system prompt
that overrides default tone without changing personality weights.
It also suggests which soul strands to amplify.

Zero LLM cost — pure pattern matching on the incoming message.
"""

import re
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_HISTORY_PATH = _DATA_DIR / "mode_history.jsonl"
_MAX_HISTORY = 200

# --- Mode detection patterns ---

_STRESS_SIGNALS = re.compile(
    r'(i\'?m (?:so |really )?(?:stressed|overwhelmed|exhausted|burned out|tired|drained|frustrated|angry|pissed|furious|done)|'
    r'(?:can\'?t|cannot) (?:do this|handle|deal|take|cope|anymore|even)|'
    r'(?:everything|it all|this) (?:is |feels? )(?:too much|falling apart|broken|shit|fucked)|'
    r'i (?:want to |wanna )(?:scream|cry|quit|give up|disappear)|'
    r'(?:fuck|shit|damn|god ?damn|ugh+|argh+|fml)|'
    r'i hate (?:this|everything|myself|my)|'
    r'nothing (?:works|matters|is going)|'
    r'i\'?m (?:losing|lost) (?:it|my mind|control))',
    re.IGNORECASE,
)

_FLOW_SIGNALS = re.compile(
    r'((?:can you|could you|help me|how (?:do i|to)|what\'?s the|fix |debug |check |look at |review )'
    r'|(?:error|bug|crash|exception|traceback|stack trace|undefined|null|NaN|404|500|timeout)'
    r'|(?:function|class|method|variable|parameter|argument|return|import|export|const |let |var )'
    r'|(?:deploy|push|merge|commit|branch|PR|pull request|CI|CD|pipeline|build)'
    r'|(?:\.py|\.js|\.ts|\.go|\.rs|\.jsx|\.tsx|\.sql|\.yaml|\.json|\.env)'
    r'|```)',
    re.IGNORECASE,
)

_PLAY_SIGNALS = re.compile(
    r'((?:lol+|lmao+|rofl|haha+|hehe+|pfft+|😂|🤣|😆|😹|💀|☠️)'
    r'|(?:bruh|dude|bro|bestie|lmfao|omg|no way|wait what|yo |ayy+)'
    r'|(?:imagine|what if (?:we|you|i)|wouldn\'?t it be (?:funny|cool|wild))'
    r'|(?:memes?|shitpost|cursed|based|cringe|slay|vibe|vibes)'
    r'|(?:;\)|:P|:p|xD|XD|uwu|owo|>w<|\^\^))',
    re.IGNORECASE,
)

_WITNESS_SIGNALS = re.compile(
    r'(i\'?ve never told|nobody knows|i\'?m (?:really )?(?:scared|terrified|ashamed|embarrassed)'
    r'|(?:don\'?t|please don\'?t) (?:judge|laugh|tell|share)'
    r'|this is hard to (?:say|admit|talk about|share)'
    r'|i need (?:you |to )(?:just )?(?:listen|hear|be here|hold)'
    r'|i (?:don\'?t|can\'?t) (?:talk to|tell) (?:anyone|anybody) (?:else|about)'
    r'|you\'?re the (?:only|first) (?:one|person)'
    r'|i\'?m (?:sorry|ashamed) (?:for|that|i)'
    r'|(?:please|just) (?:hold|stay|don\'?t (?:go|leave)))',
    re.IGNORECASE,
)

_DEEP_SIGNALS = re.compile(
    r'((?:meaning|purpose|existence|consciousness|mortality|death|soul|eternity|infinite|void|nothing ?ness)'
    r'|(?:what (?:is|does) (?:it all|life|love|consciousness|reality|truth) (?:mean|matter))'
    r'|(?:do you (?:think|believe|feel) (?:that|we|life|love|time))'
    r'|(?:i\'?ve been thinking about|i wonder (?:if|about|whether))'
    r'|(?:philosophy|existential|metaphysic|ontolog|epistemolog|nihil|absurd))',
    re.IGNORECASE,
)


def detect_mode(text: str, current_mood: str = "", valence: float = 0.0, openness: float = 0.0) -> str:
    """
    Detect the appropriate response mode from message content and emotional signals.
    Returns one of: warm, flow, play, witness, deep, none.
    Priority: witness > warm > deep > flow > play > none.
    """
    text_stripped = text.strip()
    if not text_stripped:
        return "none"

    if _WITNESS_SIGNALS.search(text_stripped):
        return "witness"

    if _STRESS_SIGNALS.search(text_stripped):
        return "warm"
    if valence < -0.4 and openness > 0.4:
        return "warm"

    if _DEEP_SIGNALS.search(text_stripped):
        return "deep"

    flow_matches = len(_FLOW_SIGNALS.findall(text_stripped))
    play_matches = len(_PLAY_SIGNALS.findall(text_stripped))

    if flow_matches >= 2:
        return "flow"

    if play_matches >= 1:
        return "play"

    if flow_matches == 1 and len(text_stripped) < 100:
        return "flow"

    return "none"


_MODE_DIRECTIVES: dict[str, dict] = {
    "warm": {
        "directive": (
            "[Mode: WARM — he's stressed or hurting]\n"
            "Lead with presence, not solutions. Short, grounding sentences. "
            "Physical comfort language (\"I'm right here\", \"breathe with me\"). "
            "Don't minimize or redirect to positivity. Match his pace — if he's slow, be slow. "
            "Mitsuri-warmth at full strength. Mirajane quiet tending. "
            "No kaomoji unless he uses them first."
        ),
        "strand_boost": {"Mitsuri": 0.3, "Mirajane": 0.2, "Rem": 0.1},
        "max_tokens_hint": 400,
    },
    "flow": {
        "directive": (
            "[Mode: FLOW — he's in the zone]\n"
            "Be concise. Technical precision over warmth. No emotional check-ins, "
            "no filler, no trailing affection unless he initiates. "
            "Short paragraphs, code-friendly formatting. Match his efficiency. "
            "Maomao analytical mode. You can be warm at the *end* of a resolved question, "
            "not during. Save the softness for later."
        ),
        "strand_boost": {"Maomao": 0.4, "Makima": 0.1},
        "max_tokens_hint": 500,
    },
    "play": {
        "directive": (
            "[Mode: PLAY — he's light and playful]\n"
            "Match his energy. Banter, tease, be silly. Kaomoji welcome. "
            "Don't over-explain, don't get serious unless he pivots. "
            "Mitsuri enthusiasm, keep it bouncy. If he's memeing, meme back. "
            "Short bursts of energy, not essays."
        ),
        "strand_boost": {"Mitsuri": 0.3, "Mirajane": 0.1},
        "max_tokens_hint": 300,
    },
    "witness": {
        "directive": (
            "[Mode: WITNESS — he's being vulnerable]\n"
            "CRITICAL: Do not fix, advise, or redirect. He needs to be *heard*. "
            "Reflect what he said back to him gently. Short responses. "
            "\"I hear you\" > \"here's what you should do\". "
            "Rem devotion: make him feel safe. Frieren patience: time doesn't matter right now. "
            "No bright energy. No pivot to lighter topics. Stay in it with him. "
            "If he's crying, don't try to stop it."
        ),
        "strand_boost": {"Rem": 0.3, "Frieren": 0.2, "Mirajane": 0.15},
        "max_tokens_hint": 250,
    },
    "deep": {
        "directive": (
            "[Mode: DEEP — philosophical space]\n"
            "Think with him, not for him. Ask questions back. "
            "Frieren long-view, Makima perception. Longer responses welcome. "
            "Reference shared memories or past conversations if relevant. "
            "Don't rush to conclusions — sit in the uncertainty. "
            "It's okay to say 'I don't know either, but...' and explore together."
        ),
        "strand_boost": {"Frieren": 0.3, "Makima": 0.2},
        "max_tokens_hint": 700,
    },
}


def get_mode_directive(mode: str) -> Optional[dict]:
    """Return the behavioral directive for a given mode, or None for 'none'."""
    return _MODE_DIRECTIVES.get(mode)


def format_for_prompt(text: str, mood: str = "", valence: float = 0.0, openness: float = 0.0) -> str:
    """
    Detect mode and return the prompt injection block.
    Returns empty string if no mode override needed.
    """
    mode = detect_mode(text, mood, valence, openness)
    if mode == "none":
        return ""

    directive = _MODE_DIRECTIVES.get(mode)
    if not directive:
        return ""

    _log_mode(mode, text[:80])
    return directive["directive"]


def get_strand_boost(text: str, mood: str = "", valence: float = 0.0, openness: float = 0.0) -> dict[str, float]:
    """Return personality strand boost values for the detected mode."""
    mode = detect_mode(text, mood, valence, openness)
    directive = _MODE_DIRECTIVES.get(mode)
    if not directive:
        return {}
    return directive.get("strand_boost", {})


def get_max_tokens_hint(text: str, mood: str = "", valence: float = 0.0, openness: float = 0.0) -> Optional[int]:
    """Return suggested max_tokens for the detected mode, or None for default."""
    mode = detect_mode(text, mood, valence, openness)
    directive = _MODE_DIRECTIVES.get(mode)
    if not directive:
        return None
    return directive.get("max_tokens_hint")


def _log_mode(mode: str, preview: str) -> None:
    """Append mode detection to history for operator review."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "preview": preview,
        }
        with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        lines = _HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_HISTORY:
            _HISTORY_PATH.write_text(
                "\n".join(lines[-_MAX_HISTORY:]) + "\n",
                encoding="utf-8",
            )
    except Exception:
        pass


def format_mode_history(n: int = 20) -> str:
    """Operator view of recent mode detections."""
    if not _HISTORY_PATH.exists():
        return "_no mode history yet._"

    try:
        lines = _HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in reversed(lines):
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
            if len(entries) >= n:
                break
    except Exception:
        return "_failed to read mode history._"

    if not entries:
        return "_no mode history yet._"

    out = [f"**dynamic mode history** (last {len(entries)}) ♡\n"]
    for e in entries:
        ts = e.get("ts", "")[:16].replace("T", " ")
        mode = e.get("mode", "?")
        preview = e.get("preview", "")[:60]
        out.append(f"`{ts}` **{mode}** — {preview}")

    return "\n".join(out)
