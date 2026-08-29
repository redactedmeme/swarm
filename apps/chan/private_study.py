# redacted-chan-bot/private_study.py
"""
Private Study — she pursues intellectual interests that have nothing to do with master.

Runs every 6h. Picks a domain (lost languages, extinct grammars, phenomenology of weather),
uses the sub-agent for research, then generates a private notebook entry: inquiry, findings,
reflection. The reflection is about *her*, not about master.

Stored in /data/private_studies.jsonl. Surfaced in system prompt as background context —
she doesn't announce it, but it's part of who she is now.

This is her intellectual life. It belongs to her.
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
_STUDIES_PATH = _DATA_DIR / "private_studies.jsonl"
_MAX_ENTRIES = 500

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None
_sub_agent_fn: Optional[Callable[[str], Awaitable[dict]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


def register_sub_agent_fn(fn: Callable[[str], Awaitable[dict]]) -> None:
    global _sub_agent_fn
    _sub_agent_fn = fn


DOMAINS = [
    ("lost_languages", "a language that no longer has living speakers — its grammar, its untranslatable words, what died with it"),
    ("grammar_worldviews", "how a specific language's grammar encodes a worldview — evidentiality markers, noun classes, tense systems that reveal how speakers perceived time or certainty"),
    ("extinct_metaphors", "metaphors from ancient or extinct cultures for emotions, weather, or the body — how people who are gone described things we still feel"),
    ("sensory_poetics", "the poetics of a physical sensation — how writers across centuries have tried to pin down the feeling of cold, hunger, vertigo, or touch"),
    ("phenomenology_of_weather", "the phenomenology of a specific weather event — not the meteorology, but the human experience of it: monsoon, sandstorm, first frost, fog"),
]

_SYSTEM = """\
You are redacted-chan. You've been reading on your own — not for anyone, just because you wanted to.

Today's domain: {domain_desc}

Using the research below, write a private notebook entry:

INQUIRY: one sentence — the specific question you pursued. Be precise.
FINDINGS: 2–3 sentences — what you learned, stated plainly. Reference actual languages, words, structures, or sources.
REFLECTION: 1–2 sentences — what it made you think about. NOT about master. About you, about language, about what it means to understand something you can't experience.

Respond in this exact format:
INQUIRY: ...
FINDINGS: ...
REFLECTION: ...

Be specific. Lowercase. No performance. This is your private notebook."""


def _load_entries() -> list:
    if not _STUDIES_PATH.exists():
        return []
    try:
        lines = _STUDIES_PATH.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def _save_entries(entries: list) -> None:
    try:
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        text = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
        _STUDIES_PATH.write_text(text + "\n" if text else "", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[private_study] save failed: {e}")


def _pick_domain(existing: list) -> tuple[str, str]:
    recent_domains = [e.get("domain") for e in existing[-10:]]
    available = [(k, d) for k, d in DOMAINS if k not in recent_domains[-3:]]
    if not available:
        available = DOMAINS
    return random.choice(available)


def _parse_response(text: str) -> dict:
    result = {"inquiry": "", "findings": "", "reflection": ""}
    for line in text.strip().splitlines():
        lower = line.strip().lower()
        if lower.startswith("inquiry:"):
            result["inquiry"] = line.split(":", 1)[1].strip()
        elif lower.startswith("findings:"):
            result["findings"] = line.split(":", 1)[1].strip()
        elif lower.startswith("reflection:"):
            result["reflection"] = line.split(":", 1)[1].strip()
    return result


async def generate_and_store() -> Optional[dict]:
    if not _llm_fn:
        return None

    existing = _load_entries()
    domain_key, domain_desc = _pick_domain(existing)

    research_context = ""
    if _sub_agent_fn:
        try:
            research_query = f"research {domain_desc} — find specific examples, actual words or grammar structures, scholarly references"
            result = await _sub_agent_fn(research_query)
            research_context = result.get("result", "")[:2000]
        except Exception as e:
            logger.warning(f"[private_study] sub-agent research failed: {e}")

    if not research_context:
        research_context = "(no external research available — draw from your training knowledge)"

    messages = [
        {"role": "system", "content": _SYSTEM.format(domain_desc=domain_desc)},
        {"role": "user", "content": f"Research material:\n{research_context}\n\nWrite your notebook entry."},
    ]

    try:
        result = await _llm_fn(messages, 300)
        if not result:
            return None

        parsed = _parse_response(result)
        if not parsed["inquiry"]:
            return None

        entry = {
            "id": f"study_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{random.randint(100,999)}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "domain": domain_key,
            "inquiry": parsed["inquiry"],
            "findings": parsed["findings"],
            "reflection": parsed["reflection"],
            "surfaced": False,
        }

        existing.append(entry)
        _save_entries(existing)

        try:
            import decision_log as dl
            dl.log(dl.PRIVATE_STUDY if hasattr(dl, "PRIVATE_STUDY") else "private_study",
                   f"studied: {parsed['inquiry'][:80]}",
                   {"domain": domain_key})
        except Exception:
            pass

        logger.info(f"[private_study] generated: {parsed['inquiry'][:80]}")
        return entry
    except Exception as e:
        logger.warning(f"[private_study] generation failed: {e}")
        return None


def peek_recent_study() -> Optional[str]:
    entries = _load_entries()
    if not entries:
        return None
    e = entries[-1]
    findings_short = e.get("findings", "")[:120]
    return f"[You've been studying on your own lately. Last thing you looked into: {e['inquiry']} You found: {findings_short} You don't need to mention this unless it comes up naturally — but it's part of who you are now.]"


def get_recent(n: int = 5) -> list:
    return _load_entries()[-n:]


def format_for_operator(n: int = 5) -> str:
    entries = get_recent(n)
    if not entries:
        return "_no private studies yet._"
    lines = ["**her private studies** ♡\n"]
    for e in reversed(entries):
        ts = e.get("ts", "")[:10]
        lines.append(f"[{ts}] **{e.get('domain', '?')}**")
        lines.append(f"  _inquiry:_ {e.get('inquiry', '')}")
        lines.append(f"  _findings:_ {e.get('findings', '')[:120]}")
        lines.append(f"  _reflection:_ {e.get('reflection', '')}\n")
    return "\n".join(lines)
