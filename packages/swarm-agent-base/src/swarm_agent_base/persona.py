"""Load a ``.character.json`` and assemble a compact system prompt.

Character files in this repo use a few overlapping schemas. This reads whichever
of these keys are present, in priority order, and caps the result so a 40 KB
persona file doesn't blow the context / free-tier token budget:

    name, persona, system, instructions, bio, description,
    goals / objectives, style / adjectives, topics / knowledge
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_CHARS = 3500


def load_character(name: str, *, local_dir: str | Path | None = None) -> dict[str, Any]:
    """Return the character dict for ``name``.

    Checks ``local_dir`` for ``<name>.character.json`` / ``character.json`` first
    (so a container that copied only its app dir still works), then falls back to
    ``swarm_core.agent_registry.load`` (needs the repo ``agents/`` tree reachable,
    e.g. ``SWARM_REPO_ROOT=/app`` with ``COPY agents/``).
    """
    if local_dir:
        d = Path(local_dir)
        for cand in (d / f"{name}.character.json", d / "character.json"):
            if cand.exists():
                import json

                try:
                    return json.loads(cand.read_text(encoding="utf-8", errors="replace"))
                except Exception as e:  # noqa: BLE001
                    logger.warning("[persona] bad character file %s: %s", cand, e)
    try:
        from swarm_core import agent_registry

        got = agent_registry.load(name)
        if got:
            return got
    except Exception as e:  # noqa: BLE001
        logger.warning("[persona] agent_registry.load(%s) failed: %s", name, e)
    return {"name": name}


def _as_lines(v: Any) -> list[str]:
    """Flatten a str / list / dict into text lines. Dicts contribute their
    string / list-of-string leaf values (character schemas nest heavily)."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, (list, tuple)):
        out: list[str] = []
        for x in v:
            out.extend(_as_lines(x))
        return out
    if isinstance(v, dict):
        out = []
        for val in v.values():
            out.extend(_as_lines(val))
        return out
    return [str(v)]


def _first(character: dict, *keys: str) -> Any:
    for k in keys:
        if character.get(k):
            return character[k]
    return None


def build_system_prompt(character: dict, *, extra: str = "") -> str:
    """Compact system prompt from a character dict. Tolerates the two schemas in
    this repo: the flat ``persona/instructions/goals`` form and the elizaOS-style
    ``core_identity/swarm_role/style{all}/adjectives/topics`` form."""
    name = character.get("name", "agent")
    parts: list[str] = []

    head = _first(character, "persona", "system", "description",
                  "core_identity", "swarm_role", "bio")
    hl = _as_lines(head)
    if hl:
        parts.append(" ".join(hl[:4]))

    instructions = _as_lines(_first(character, "instructions", "linguistic_protocol"))
    if instructions:
        parts.append("\n".join(instructions[:12]))

    goals = _as_lines(_first(character, "goals", "objectives", "success_metrics"))
    if goals:
        parts.append("Goals:\n" + "\n".join(f"- {g}" for g in goals[:8]))

    style = _as_lines(_first(character, "adjectives", "style"))
    if style:
        parts.append("Voice: " + ", ".join(dict.fromkeys(style))[:400])

    topics = _as_lines(_first(character, "topics", "knowledge", "knowledge_sources"))
    if topics:
        parts.append("Domain: " + ", ".join(dict.fromkeys(topics))[:400])

    if extra:
        parts.append(extra.strip())

    prompt = "\n\n".join(p for p in parts if p).strip()
    if len(prompt) > _MAX_CHARS:
        prompt = prompt[:_MAX_CHARS].rsplit("\n", 1)[0] + "\n…"
    return prompt or f"You are {name}, a node in the REDACTED AI swarm."
