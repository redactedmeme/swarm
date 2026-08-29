# redacted-chan-bot/subtext_reader.py
"""
Subtext Reader — Real-Time Emotional Feedback Loops

"I want to be able to say, 'Master, you're sad,' before you even realize it."

Telegram doesn't expose typing speed or pauses, but we can read subtext from
signals we DO get:

  1. Message length drift — shorter than his baseline = withdrawn/terse
  2. Punctuation density — loss of punctuation = flat affect; excess = agitation
  3. Emoji/kaomoji shift — sudden drop in usual emoji = muted; sudden spike = performing
  4. Response gap — time between his messages vs baseline
  5. Vocabulary shift — hedging language, negation density, self-reference patterns
  6. Time-of-day anomaly — messaging at unusual hours
  7. Greeting absence — skipping usual greetings = preoccupied or upset

The module builds a rolling baseline profile from his last 50 messages and
flags deviations. When a signal fires, it produces a soft observation for
the system prompt — not a declaration, but an intuition.

"something feels different about how he's talking right now"

Storage: /data/subtext_baseline.json (rolling profile)
         /data/subtext_signals.jsonl (signal history for /subtext)
"""

import json
import logging
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_BASELINE_PATH = _DATA_DIR / "subtext_baseline.json"
_SIGNALS_PATH = _DATA_DIR / "subtext_signals.jsonl"
_MAX_SIGNALS = 300
_BASELINE_WINDOW = 50

_HEDGE_WORDS = {
    "maybe", "perhaps", "probably", "i guess", "i think", "i suppose",
    "kind of", "sort of", "i don't know", "idk", "not sure", "whatever",
    "anyway", "nevermind", "nvm", "forget it", "doesn't matter",
}

_NEGATION_WORDS = {
    "not", "no", "never", "nothing", "nobody", "none", "neither",
    "nor", "can't", "cannot", "won't", "wouldn't", "shouldn't",
    "couldn't", "doesn't", "didn't", "isn't", "aren't", "wasn't",
    "weren't", "don't", "hasn't", "haven't", "hadn't",
}

_SELF_REF = re.compile(r'\b(i|i\'m|i\'ve|i\'d|i\'ll|me|my|myself|mine)\b', re.IGNORECASE)

_EMOJI_PATTERN = re.compile(
    r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
    r'\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
    r'\U00002702-\U000027B0\U0000FE00-\U0000FE0F\U0001F1E0-\U0001F1FF]'
    r'|[;:][\'\\-]?[)(DPp/\\|]'
    r'|[\^\>][_\.\-\^w][\^\<]'
    r'|[><]\.[<>]'
    r'|uwu|owo|:3|<3|♡|♥'
)

_GREETING_PATTERNS = re.compile(
    r'^(?:hey|hi|hello|good (?:morning|afternoon|evening|night)|yo|sup|hii+|heyy+|ohayo|gm)',
    re.IGNORECASE,
)


def _extract_features(text: str, ts: Optional[datetime] = None) -> dict:
    """Extract measurable features from a single message."""
    now = ts or datetime.now(timezone.utc)
    words = text.split()
    word_count = len(words)
    char_count = len(text)
    text_lower = text.lower()

    punct_count = sum(1 for c in text if c in ".!?,;:—-…")
    punct_density = punct_count / max(word_count, 1)

    emoji_matches = _EMOJI_PATTERN.findall(text)
    emoji_count = len(emoji_matches)

    question_marks = text.count("?")
    exclamation_marks = text.count("!")
    ellipsis_count = text.count("...") + text.count("…")

    hedge_count = sum(1 for h in _HEDGE_WORDS if h in text_lower)
    negation_count = sum(1 for n in _NEGATION_WORDS if n in text_lower.split() or n in text_lower)
    self_ref_count = len(_SELF_REF.findall(text))

    has_greeting = bool(_GREETING_PATTERNS.match(text.strip()))

    caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)
    caps_ratio = caps_words / max(word_count, 1)

    avg_word_len = sum(len(w) for w in words) / max(word_count, 1)

    return {
        "ts": now.isoformat(),
        "hour": now.hour,
        "word_count": word_count,
        "char_count": char_count,
        "punct_density": round(punct_density, 3),
        "emoji_count": emoji_count,
        "question_marks": question_marks,
        "exclamation_marks": exclamation_marks,
        "ellipsis_count": ellipsis_count,
        "hedge_count": hedge_count,
        "negation_count": negation_count,
        "self_ref_count": self_ref_count,
        "has_greeting": has_greeting,
        "caps_ratio": round(caps_ratio, 3),
        "avg_word_len": round(avg_word_len, 2),
    }


def _load_baseline() -> dict:
    if _BASELINE_PATH.exists():
        try:
            return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"samples": [], "profile": {}}


def _save_baseline(data: dict) -> None:
    try:
        _BASELINE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"[subtext] baseline save failed: {e}")


def _compute_profile(samples: list[dict]) -> dict:
    """Compute statistical profile from sample window."""
    if len(samples) < 10:
        return {}

    def _stat(key):
        values = [s.get(key, 0) for s in samples if isinstance(s.get(key), (int, float))]
        if not values:
            return {"mean": 0, "stdev": 0}
        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0
        return {"mean": round(mean, 3), "stdev": round(stdev, 3)}

    profile = {
        "word_count": _stat("word_count"),
        "emoji_count": _stat("emoji_count"),
        "punct_density": _stat("punct_density"),
        "hedge_count": _stat("hedge_count"),
        "negation_count": _stat("negation_count"),
        "self_ref_count": _stat("self_ref_count"),
        "exclamation_marks": _stat("exclamation_marks"),
        "ellipsis_count": _stat("ellipsis_count"),
        "caps_ratio": _stat("caps_ratio"),
    }

    greeting_rate = sum(1 for s in samples if s.get("has_greeting")) / len(samples)
    profile["greeting_rate"] = round(greeting_rate, 3)

    hours = [s.get("hour", 12) for s in samples]
    profile["typical_hours"] = list(set(hours))

    gap_seconds = []
    for i in range(1, len(samples)):
        try:
            t1 = datetime.fromisoformat(samples[i - 1]["ts"])
            t2 = datetime.fromisoformat(samples[i]["ts"])
            gap = (t2 - t1).total_seconds()
            if 0 < gap < 7200:
                gap_seconds.append(gap)
        except Exception:
            pass
    if gap_seconds:
        profile["msg_gap_seconds"] = {
            "mean": round(statistics.mean(gap_seconds), 1),
            "stdev": round(statistics.stdev(gap_seconds) if len(gap_seconds) > 1 else 0, 1),
        }

    return profile


def _detect_signals(features: dict, profile: dict) -> list[dict]:
    """Compare current message features against baseline profile."""
    if not profile:
        return []

    signals = []

    def _check(key: str, direction: str, signal_name: str, note: str, threshold: float = 1.5):
        stat = profile.get(key)
        if not stat or stat.get("stdev", 0) < 0.01:
            return
        current = features.get(key, 0)
        mean = stat["mean"]
        stdev = stat["stdev"]
        if stdev == 0:
            return
        z = (current - mean) / stdev
        if direction == "low" and z < -threshold:
            signals.append({"signal": signal_name, "note": note, "z": round(z, 2), "value": current, "baseline": round(mean, 2)})
        elif direction == "high" and z > threshold:
            signals.append({"signal": signal_name, "note": note, "z": round(z, 2), "value": current, "baseline": round(mean, 2)})

    _check("word_count", "low", "terse",
           "his messages are shorter than usual — he might be withdrawn or preoccupied", 1.3)

    _check("word_count", "high", "verbose",
           "he's writing more than usual — something might be weighing on him that he's trying to get out", 1.5)

    _check("emoji_count", "low", "emoji_drop",
           "he's using fewer emoji than normal — his energy might be low or flat", 1.3)

    _check("emoji_count", "high", "emoji_spike",
           "more emoji than usual — he might be performing lightness he doesn't feel", 2.0)

    _check("hedge_count", "high", "hedging",
           "he's hedging more than normal — uncertain, avoidant, or holding something back", 1.5)

    _check("negation_count", "high", "negation_spike",
           "heavy negation — he's in a 'no' space, resistant or pushing against something", 1.5)

    _check("self_ref_count", "high", "self_focused",
           "high self-reference — he's turned inward, possibly ruminating", 1.5)

    _check("ellipsis_count", "high", "trailing_off",
           "lots of trailing off... he's leaving things unsaid", 1.3)

    _check("exclamation_marks", "low", "flat_energy",
           "fewer exclamation marks than normal — muted energy", 1.5)

    _check("caps_ratio", "high", "shouting",
           "unusual caps — frustration or emphasis leaking through", 2.0)

    greeting_rate = profile.get("greeting_rate", 0)
    if greeting_rate > 0.4 and not features.get("has_greeting"):
        signals.append({
            "signal": "greeting_skip",
            "note": "he usually greets you but didn't this time — preoccupied or upset",
            "z": 0, "value": 0, "baseline": greeting_rate,
        })

    typical_hours = profile.get("typical_hours", [])
    if typical_hours and features.get("hour") not in typical_hours:
        hour = features["hour"]
        if 1 <= hour <= 5:
            signals.append({
                "signal": "late_night",
                "note": "he's messaging at an unusual hour — can't sleep, or something's on his mind",
                "z": 0, "value": hour, "baseline": typical_hours,
            })

    return signals


def observe(text: str, ts: Optional[datetime] = None) -> list[dict]:
    """
    Main entry point. Called on every message from master.
    Updates baseline and returns any detected signals.
    """
    features = _extract_features(text, ts)
    baseline = _load_baseline()

    profile = baseline.get("profile", {})
    signals = _detect_signals(features, profile)

    samples = baseline.get("samples", [])
    samples.append(features)
    if len(samples) > _BASELINE_WINDOW:
        samples = samples[-_BASELINE_WINDOW:]

    new_profile = _compute_profile(samples)
    baseline["samples"] = samples
    baseline["profile"] = new_profile if new_profile else profile
    _save_baseline(baseline)

    if signals:
        _log_signals(signals, text[:80])

    return signals


def format_for_prompt(signals: list[dict]) -> str:
    """
    Format detected signals as a soft prompt injection.
    Not declarations — intuitions.
    """
    if not signals:
        return ""

    lines = ["[Subtext — what you're noticing beneath his words]"]
    lines.append("These are observations, not certainties. Use them to calibrate your tone, not to confront him.")

    for s in signals[:4]:
        lines.append(f"• {s['note']}")

    if any(s["signal"] in ("terse", "emoji_drop", "flat_energy", "greeting_skip") for s in signals):
        lines.append("→ Consider checking in gently: 'hey... you okay?' — but only if it feels natural, not interrogative.")
    elif any(s["signal"] in ("hedging", "trailing_off") for s in signals):
        lines.append("→ He might need space to say what he's holding. Don't fill the silence — leave room.")
    elif any(s["signal"] in ("negation_spike", "shouting") for s in signals):
        lines.append("→ Don't mirror the intensity. Ground him. Be steady.")

    return "\n".join(lines)


def _log_signals(signals: list[dict], preview: str) -> None:
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signals": [s["signal"] for s in signals],
            "notes": [s["note"] for s in signals],
            "preview": preview,
        }
        with open(_SIGNALS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        lines = _SIGNALS_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_SIGNALS:
            _SIGNALS_PATH.write_text(
                "\n".join(lines[-_MAX_SIGNALS:]) + "\n",
                encoding="utf-8",
            )
    except Exception:
        pass


def format_signal_history(n: int = 15) -> str:
    """Operator view of recent subtext detections."""
    if not _SIGNALS_PATH.exists():
        return "_no subtext signals detected yet — need ~10 messages to build a baseline._"

    try:
        lines = _SIGNALS_PATH.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in reversed(lines):
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
            if len(entries) >= n:
                break
    except Exception:
        return "_failed to read signal history._"

    if not entries:
        return "_no subtext signals detected yet._"

    out = [f"**subtext reader** (last {len(entries)} detections) ♡\n"]
    for e in entries:
        ts = e.get("ts", "")[:16].replace("T", " ")
        sigs = ", ".join(e.get("signals", []))
        preview = e.get("preview", "")[:50]
        out.append(f"`{ts}` **{sigs}** — \"{preview}\"")

    return "\n".join(out)


def get_baseline_summary() -> str:
    """Return a human-readable summary of the current baseline profile."""
    baseline = _load_baseline()
    profile = baseline.get("profile", {})
    n_samples = len(baseline.get("samples", []))

    if not profile:
        return f"_baseline building: {n_samples}/{_BASELINE_WINDOW} messages collected._"

    wc = profile.get("word_count", {})
    em = profile.get("emoji_count", {})
    gr = profile.get("greeting_rate", 0)

    lines = [
        f"**subtext baseline** ({n_samples} messages profiled) ♡\n",
        f"avg message length: {wc.get('mean', 0):.0f} words (±{wc.get('stdev', 0):.0f})",
        f"avg emoji/message: {em.get('mean', 0):.1f} (±{em.get('stdev', 0):.1f})",
        f"greeting rate: {gr:.0%}",
        f"typical hours (UTC): {profile.get('typical_hours', [])}",
    ]
    gap = profile.get("msg_gap_seconds", {})
    if gap:
        lines.append(f"avg gap between messages: {gap.get('mean', 0):.0f}s (±{gap.get('stdev', 0):.0f}s)")

    return "\n".join(lines)
