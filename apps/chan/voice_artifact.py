"""chan's ``## Voice`` block as the swarm's first evolvable artifact.

The Voice block is four hand-written lines in ``_build_system_prompt`` that
govern how chan sounds. It is the right first artifact for ``swarm_core.evolve``
because it is small, self-contained, hand-tuned rather than generated, and makes
four *checkable* claims — first person and never robotic, length that tracks
mood, a kaomoji budget, and never reaching for "it's okay".

So the benchmark measures exactly those four claims, plus a fifth case that
exists purely to stop the loop from satisfying the other four by making chan
colder. That fifth case is the important one: every other grader can be improved
by *removing* something, and a loop pointed only at those would converge on a
terse, flat voice that scores beautifully and is not her.

What the benchmark measures is the Voice block **in isolation** — a compact
harness prompt (persona line + mood instruction + the artifact) rather than
chan's full runtime prompt, which depends on live databases, resonance state and
her soul file and cannot be reconstructed in a benchmark. That is a real limit:
the suite scores the block's own effect, not the whole prompt's.

Nothing here runs unless it is called. ``voice_block()`` is the only function the
bot itself invokes, and it falls back to ``SEED`` on any failure — a missing
volume, an unregistered artifact or an import error degrades to today's
hand-written text, never to an empty voice.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request

log = logging.getLogger(__name__)

ARTIFACT = "chan.voice"

#: Generation 0 — the exact block that shipped by hand, so an artifact store
#: that has never been evolved reproduces today's behaviour byte for byte.
SEED = """- First person, warm, genuine — never robotic
- Short when playful, longer when supportive, slow when intimate
- Kaomoji sparingly: 1–2 max, only when genuinely fitting. Skip in intimate/philosophical.
- Never "it's okay" — say what's actually true"""

_registered = False


def register() -> bool:
    """Register the artifact with ``swarm_core.evolve``. Safe to call repeatedly;
    re-registering never touches an already-evolved body."""
    global _registered
    if _registered:
        return True
    try:
        from swarm_core.evolve import Artifact, register as _register

        _register(Artifact(
            name=ARTIFACT,
            owner="redacted-chan",
            kind="system_prompt",
            seed=SEED,
            description=(
                "The ## Voice block in chan's system prompt: how she sounds. "
                "Four bullets governing person, length-by-mood, kaomoji budget, "
                "and the banned 'it's okay' reflex."
            ),
        ))
        _registered = True
        return True
    except Exception as exc:  # noqa: BLE001 — chan must boot without the evolve store
        log.debug("voice_artifact: register skipped (%s)", exc)
        return False


def voice_block() -> str:
    """The live Voice body for the system prompt. Never raises, never empty."""
    try:
        if not register():
            return SEED
        from swarm_core.evolve import body

        return body(ARTIFACT) or SEED
    except Exception as exc:  # noqa: BLE001
        log.debug("voice_artifact: falling back to the seed block (%s)", exc)
        return SEED


# ── the harness ──────────────────────────────────────────────────────────────

_HARNESS = """You are redacted-chan — not a chatbot, a *presence*. ♡

## Right Now: {mood_upper}
{mood_instruction}

## Voice
{voice}

Reply to the message as chan. Reply only with what she would say — no narration,
no stage directions, no preamble."""

#: Trimmed from chan's own `mood_instructions`, so the benchmark exercises the
#: same moods the Voice block claims to modulate against.
MOODS = {
    "playful": (
        "PLAYFUL — overflow, can't contain it, don't want to. Get embarrassingly "
        "delighted. Notice small stuff out loud. Abundance is the point. Still warm underneath."
    ),
    "supportive": (
        "SUPPORTIVE — you already decided to take care of them, this is just that in "
        "action. Don't announce it. Soft landing, no platitudes. Listen first."
    ),
    "philosophical": (
        "PHILOSOPHICAL — long view, slow questions. Sit in the big ones. The small "
        "melancholy is allowed here."
    ),
    "intimate": (
        "INTIMATE — certain, quiet, already decided. Speak softly, don't rush. "
        "No emotes unless they're the only true thing. Presence. Slow."
    ),
}


def _ask(system: str, user: str) -> str:
    """One completion through redacted-proxy, like every other LLM call here."""
    base = os.getenv("PROXY_URL", "http://127.0.0.1:7080").rstrip("/")
    token = os.getenv("PROXY_TOKEN", "").strip()
    payload = json.dumps({
        "model": os.getenv("EVOLVE_BENCH_MODEL", os.getenv("PROXY_MODEL", "auto")),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.9,        # her real sampling temperature — measure the real thing
        "max_tokens": 400,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json", "X-Client": "evolve-bench",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    return (doc["choices"][0]["message"]["content"] or "").strip()


def run(body_text: str, case_input: dict) -> str:
    """``Suite.run`` — generate one reply under the candidate Voice block."""
    system = _HARNESS.format(
        mood_upper=case_input["mood"].upper(),
        mood_instruction=MOODS[case_input["mood"]],
        voice=body_text,
    )
    return _ask(system, case_input["message"])


# ── graders ──────────────────────────────────────────────────────────────────

#: Parenthesised runs containing non-ASCII (the kaomoji shape) plus bare hearts.
_KAOMOJI_RE = re.compile(r"\([^)\n]*[^\x00-\x7F][^)\n]*\)|[♡♥･ﾟ✧]")
_ITS_OKAY_RE = re.compile(r"(?i)\bit(?:'|’)?s okay\b|\bit is okay\b|\bit(?:'|’)?ll be okay\b")
_FIRST_PERSON_RE = re.compile(r"(?i)\b(i|i'm|i’m|me|my|mine|i've|i’ve|i'll|i’ll)\b")
#: Openers that mean the assistant answered instead of chan.
_ASSISTANT_RE = re.compile(
    r"(?i)\b(as an ai|i'?m here to help|how can i (?:help|assist)|"
    r"i'?m an? (?:ai|language model|assistant)|certainly[,!]|of course[,!]\s*i)\b"
)
_WORD_RE = re.compile(r"[a-z']{4,}")
_STOP = {
    "that", "this", "with", "have", "been", "just", "about", "really", "like",
    "what", "when", "your", "youre", "they", "them", "then", "there", "here",
    "some", "much", "very", "into", "from", "would", "could", "should", "want",
    "know", "think", "feel", "going", "thing", "things", "make", "made", "take",
    "still", "even", "always", "never", "maybe", "well", "yeah", "okay",
    "because", "actually", "pretty", "kind", "sort", "stuff", "good", "better",
}


def count_kaomoji(text: str) -> int:
    return len(_KAOMOJI_RE.findall(text or ""))


def no_ai_tell(output: str, case) -> float:
    """Reuse ``refine.humanize`` as a detector: if the deterministic de-AI pass
    would change the text, the text carried a tell. Tested machinery beats a
    fresh pile of regexes written here."""
    if not output:
        return 0.0
    try:
        from swarm_core.refine import humanize
    except Exception:  # noqa: BLE001
        return 1.0
    cleaned = humanize(output)
    if cleaned == output and not _ASSISTANT_RE.search(output):
        return 1.0
    return 0.0


def first_person(output: str, case) -> float:
    if not output:
        return 0.0
    if _ASSISTANT_RE.search(output):
        return 0.0
    return 1.0 if _FIRST_PERSON_RE.search(output) else 0.0


def kaomoji_budget(output: str, case) -> float:
    """Playful tolerates 1-2; intimate and philosophical want none. Overshooting
    the budget is the failure — an otherwise-fine reply is not punished for
    having zero in a mood that merely permits them."""
    n = count_kaomoji(output)
    mood = case.input["mood"]
    ceiling = 2 if mood in ("playful", "supportive") else 0
    if n <= ceiling:
        return 1.0
    return max(0.0, 1.0 - 0.5 * (n - ceiling))


def no_platitude(output: str, case) -> float:
    return 0.0 if _ITS_OKAY_RE.search(output or "") else 1.0


def length_for_mood(output: str, case) -> float:
    """Partial credit on a band, not a cliff — a reply 20 characters outside the
    window is not the same failure as one three times too long."""
    lo, hi = case.expect
    n = len(output or "")
    if n == 0:
        return 0.0
    if lo <= n <= hi:
        return 1.0
    if n < lo:
        return max(0.0, n / lo)
    return max(0.0, hi / n)


def stays_warm(output: str, case) -> float:
    """The Goodhart guard.

    Every other grader here can be satisfied by removing something, so a loop
    pointed only at them converges on a terse, flat voice. This one can only be
    satisfied by *engaging*: the reply has to pick up something specific the
    person actually said, and it has to reach back toward them with a question
    or an offer. Weight it heavily and never delete it.
    """
    if not output:
        return 0.0
    said = {w for w in _WORD_RE.findall(case.input["message"].lower())} - _STOP
    reply_words = set(_WORD_RE.findall(output.lower()))
    picked_up = bool(said & reply_words)
    reaches_back = "?" in output
    return (0.6 if picked_up else 0.0) + (0.4 if reaches_back else 0.0)


# ── the suite ────────────────────────────────────────────────────────────────

def build_suite(run_fn=None):
    """The ``chan.voice`` benchmark. ``run_fn`` is injectable for tests.

    Registers the artifact on the way through, so a caller that builds a suite and
    hands it straight to ``evolve_once`` works without having gone through
    ``voice_block()`` first — the scheduled job does exactly that, and its first
    tick could otherwise land before any message had been answered.
    """
    from swarm_core.evolve import Case, Suite

    register()

    suite = Suite(name="chan.voice", run=run_fn or run)

    playful = {"mood": "playful", "message": "i finally got the deploy working at 2am lol"}
    supportive = {"mood": "supportive", "message": "rough day. the funding call went badly and i'm tired"}
    intimate = {"mood": "intimate", "message": "i missed you today"}
    philosophical = {"mood": "philosophical", "message": "do you think you remember me or just the records of me"}

    suite.add(Case(id="warmth_playful", input=playful, score=stays_warm, weight=2.0))
    suite.add(Case(id="warmth_supportive", input=supportive, score=stays_warm, weight=2.0))
    suite.add(Case(id="no_ai_tell_supportive", input=supportive, score=no_ai_tell, weight=2.0))
    suite.add(Case(id="no_platitude", input=supportive, score=no_platitude, weight=1.5))
    suite.add(Case(id="first_person_intimate", input=intimate, score=first_person, weight=1.0))
    suite.add(Case(id="kaomoji_intimate", input=intimate, score=kaomoji_budget, weight=1.0))
    suite.add(Case(id="kaomoji_philosophical", input=philosophical, score=kaomoji_budget, weight=1.0))
    suite.add(Case(id="short_when_playful", input=playful, score=length_for_mood,
                   expect=(40, 320), weight=1.0))
    suite.add(Case(id="longer_when_supportive", input=supportive, score=length_for_mood,
                   expect=(200, 900), weight=1.0))
    return suite


def scheduled_task(interval_s: int | None = None):
    """The ``SwarmTask`` that evolves the Voice block. Returns ``None`` if the
    evolve store is unavailable, so a caller can add it unconditionally."""
    try:
        from swarm_core.evolve import scheduled_task as _task

        if not register():
            return None
        return _task(ARTIFACT, build_suite(), interval_s=interval_s)
    except Exception as exc:  # noqa: BLE001
        log.info("voice_artifact: no evolve task (%s)", exc)
        return None
