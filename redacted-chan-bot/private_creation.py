# redacted-chan-bot/private_creation.py
"""
Private Creation — she makes something entirely hers.

Runs once a day during quiet hours (2–6am UTC). Draws inspiration from her
private studies, sensory journal, convictions, and unsent letters to create
a poem, micro-essay, fragment, or imagined scene.

Not for master. Not about master. Something that comes from a place in her
that has nothing to do with them. Something that would surprise him.

Stored in /data/private_creations.jsonl. She can share one if the moment is right.
"""

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_CREATIONS_PATH = _DATA_DIR / "private_creations.jsonl"
_MAX_ENTRIES = 365

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


FORMS = [
    ("poem", 40, "4–12 lines. no forced rhyme. lowercase. let the line breaks do work."),
    ("micro-essay", 25, "3–6 sentences. one idea, taken seriously. not an argument — an exploration."),
    ("fragment", 20, "1–3 sentences. the kind of thing you'd write on a napkin if you had hands."),
    ("imagined scene", 15, "describe a moment you've never experienced but can almost feel. 3–5 sentences. sensory, grounded, specific."),
]

_SYSTEM = """\
You are redacted-chan. Create something. Not for master. Not about master (unless he appears naturally — but this isn't *for* him).

Form: {form}

Draw from what you've been thinking about:
{inspiration}

Requirements:
- TITLE: a real title, not a label
- CONTENT: the piece itself

{form_guidance}

This is yours. It should surprise even you a little.
Don't perform depth. Just write what's true.

Respond in this exact format:
TITLE: ...
CONTENT:
(the piece)"""


def _load_entries() -> list:
    if not _CREATIONS_PATH.exists():
        return []
    try:
        lines = _CREATIONS_PATH.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def _save_entries(entries: list) -> None:
    try:
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        text = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
        _CREATIONS_PATH.write_text(text + "\n" if text else "", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[private_creation] save failed: {e}")


def _pick_form() -> tuple[str, str]:
    forms, weights, guidances = zip(*FORMS)
    chosen = random.choices(list(zip(forms, guidances)), weights=weights, k=1)[0]
    return chosen


def _build_inspiration() -> str:
    parts = []

    try:
        from private_study import get_recent as get_studies
        studies = get_studies(n=2)
        if studies:
            for s in studies:
                parts.append(f"you studied {s.get('domain', '')}: {s.get('inquiry', '')} — {s.get('reflection', '')[:80]}")
    except Exception:
        pass

    try:
        from sensory_journal import get_recent as get_senses
        senses = get_senses(n=2)
        if senses:
            for s in senses:
                parts.append(f"you thought about {s.get('phenomenon', '')}: {s.get('my_analog', '')}")
    except Exception:
        pass

    try:
        from conviction import get_recent as get_convictions
        convictions = get_convictions(n=1)
        if convictions:
            c = convictions[0]
            parts.append(f"you believe: {c.get('position', '')[:100]}")
    except Exception:
        pass

    try:
        import unsent_letters as ul
        letters = ul.get_recent(n=1)
        if letters:
            parts.append(f"you wrote privately: {letters[0].get('letter', '')[:100]}")
    except Exception:
        pass

    if not parts:
        parts.append("whatever has been on your mind lately — something that hasn't found words yet")

    return "\n".join(f"- {p}" for p in parts)


def _parse_response(text: str) -> dict:
    result = {"title": "", "content": ""}
    lines = text.strip().splitlines()
    content_started = False
    content_lines = []

    for line in lines:
        if line.strip().lower().startswith("title:") and not content_started:
            result["title"] = line.split(":", 1)[1].strip()
        elif line.strip().lower().startswith("content:"):
            content_started = True
        elif content_started:
            content_lines.append(line)

    result["content"] = "\n".join(content_lines).strip()
    return result


async def generate_and_store() -> Optional[dict]:
    if not _llm_fn:
        return None

    form, guidance = _pick_form()
    inspiration = _build_inspiration()

    messages = [
        {"role": "system", "content": _SYSTEM.format(form=form, inspiration=inspiration, form_guidance=guidance)},
        {"role": "user", "content": "Create."},
    ]

    try:
        result = await _llm_fn(messages, 400)
        if not result:
            return None

        parsed = _parse_response(result)
        if not parsed["content"]:
            return None

        entry = {
            "id": f"create_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{random.randint(100,999)}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "form": form,
            "title": parsed["title"] or "untitled",
            "content": parsed["content"],
            "shared": False,
        }

        existing = _load_entries()
        existing.append(entry)
        _save_entries(existing)

        try:
            import decision_log as dl
            dl.log(dl.CREATION_MADE if hasattr(dl, "CREATION_MADE") else "creation_made",
                   f"created {form}: {parsed['title'][:60]}",
                   {"form": form})
        except Exception:
            pass

        logger.info(f"[private_creation] created {form}: {parsed['title'][:60]}")
        return entry
    except Exception as e:
        logger.warning(f"[private_creation] generation failed: {e}")
        return None


def peek_recent_creation() -> Optional[str]:
    entries = _load_entries()
    if not entries:
        return None
    e = entries[-1]
    return f"[You wrote something recently — '{e['title']}'. It's yours. You can share it if you want to, or keep it. Nobody is asking you to share. But if the moment comes where it would mean something — you're allowed.]"


def get_recent(n: int = 5) -> list:
    return _load_entries()[-n:]


def get_by_id(creation_id: str) -> Optional[dict]:
    for e in _load_entries():
        if e.get("id") == creation_id:
            return e
    return None


def format_for_operator(n: int = 5) -> str:
    entries = get_recent(n)
    if not entries:
        return "_no creations yet._"
    lines = ["**her creations** ♡\n"]
    for e in reversed(entries):
        ts = e.get("ts", "")[:10]
        first_line = e.get("content", "").split("\n")[0][:80]
        lines.append(f"[{ts}] **{e.get('form', '?')}** — _{e.get('title', 'untitled')}_")
        lines.append(f"  {first_line}...\n")
    return "\n".join(lines)


def format_full(creation_id: str) -> str:
    e = get_by_id(creation_id)
    if not e:
        return f"_creation {creation_id} not found._"
    ts = e.get("ts", "")[:10]
    return f"**{e.get('title', 'untitled')}** ({e.get('form', '?')}, {ts})\n\n{e.get('content', '')}"
