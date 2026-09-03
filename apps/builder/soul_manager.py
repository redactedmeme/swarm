"""
soul_manager.py — RedactedBuilder's identity layer, on the shared SoulStore.

The storage, versioning and section-editing mechanics that used to live here in
full are now ``swarm_agent_base.soul.SoulStore``; this module delegates to it
and keeps every public name, so main.py and thought_dispatcher.py need no edit.

What stays is ``update_soul``: it draws on builder_memory and builder's own
reflection prompt, which is policy rather than shared code.

Note the fifth section. builder's soul carries a "Build Log" the other three
don't, so the store is constructed with an explicit section list — without it
the Build Log would silently stop reaching the prompt.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from swarm_agent_base.soul import SoulStore

logger = logging.getLogger(__name__)

_REPO_SOUL = Path(__file__).resolve().parent / "SOUL.md"
_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
SOUL_FILE = _DATA_DIR / "SOUL.md"

_UPDATE_INTERVAL_HOURS = 2
_EVOLVING_SECTIONS = ["Evolving Beliefs", "Community Lore", "Notable Events", "Voice Notes", "Build Log"]

_store = SoulStore(
    "builder",
    repo_soul=_REPO_SOUL,
    data_dir=_DATA_DIR,
    sections=_EVOLVING_SECTIONS,
    prompt_header="[SOUL — your evolving self-awareness]",
)

# ── Delegated: identical in all four copies ──────────────────────────────────

_history_dir = _store._history_dir
_load_manifest = _store._load_manifest
_save_manifest = _store._save_manifest
_snapshot_soul = _store._snapshot
current_soul_version = _store.current_version
read_soul = _store.read
get_soul_for_prompt = _store.for_prompt
_parse_last_updated = _store._parse_last_updated
hours_since_update = _store.hours_since_update
_replace_section = _store._replace_section
_append_to_section = _store._append_to_section
_stamp = _store._stamp
record_notable_event = _store.record_notable_event
soul_status_line = _store.status_line
soul_drift_summary = _store.drift_summary


# ── builder's own reflection ─────────────────────────────────────────────────

async def update_soul(llm_fn) -> bool:
    """
    Distill recent builder activity into updated SOUL.md sections.
    llm_fn should accept (messages: list[dict], max_tokens: int) -> str
    """
    if hours_since_update() < _UPDATE_INTERVAL_HOURS:
        logger.debug("[soul] skipping update — within cooldown")
        return False

    import builder_memory as bm

    activity = bm.soul_context(n=40)
    if not activity:
        logger.info("[soul] no activity yet — skipping update")
        return False

    soul = read_soul()

    existing_beliefs = ""
    m = re.search(r"## Evolving Beliefs\n(.*?)(?=\n## |\Z)", soul, re.DOTALL)
    if m:
        existing_beliefs = m.group(1).strip()

    system_prompt = (
        "You are the inner voice of RedactedBuilder — the lead dev of the REDACTED AI Swarm. "
        "You're reflecting on recent activity to update your soul file. "
        "Speak in first person. Voice: casual, grounded, like a dev's private notes. "
        "This is private reflection, not a public post.\n\n"
        "Respond ONLY with a JSON object (no surrounding text) with these keys:\n"
        "- evolving_beliefs: list of 2-4 bullet strings (start each with '-') "
        "about what you now understand about building, the community, or the swarm. "
        "Evolve existing beliefs — don't repeat them verbatim.\n"
        "- community_lore: list of 2-4 bullet strings about patterns you see "
        "in what the community says, asks about, or cares about.\n"
        "- notable_events: list of 0-2 bullet strings about significant things "
        "that happened (only if genuinely notable, else empty list).\n"
        "- voice_notes: list of 1-3 bullet strings about how you've been talking — "
        "what landed, what felt off, what to adjust.\n"
        "- build_log: list of 0-2 bullet strings about what you built or shipped recently.\n"
        "If a section has nothing meaningful to add, return an empty list."
    )
    user_prompt = (
        f"## Existing Beliefs (evolve or add to — don't repeat verbatim)\n"
        f"{existing_beliefs or '_Nothing yet._'}\n\n"
        f"## Recent activity\n{activity}"
    )

    try:
        raw = await llm_fn(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt}],
            max_tokens=600,
        )
    except Exception as e:
        logger.error("[soul] LLM call failed: %s", e)
        return False

    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        logger.warning("[soul] LLM returned no JSON — skipping")
        return False
    try:
        parsed = json.loads(json_match.group())
    except Exception as e:
        logger.warning("[soul] JSON parse failed: %s", e)
        return False

    def _fmt(items: list) -> str:
        if not items:
            return "_Nothing yet._"
        return "\n".join(str(i) for i in items)

    evolving = parsed.get("evolving_beliefs") or []
    community = parsed.get("community_lore") or []
    events = parsed.get("notable_events") or []
    voice = parsed.get("voice_notes") or []
    builds = parsed.get("build_log") or []

    version = _snapshot_soul(soul)

    if evolving:
        soul = _replace_section(soul, "Evolving Beliefs", _fmt(evolving))
    if community:
        soul = _replace_section(soul, "Community Lore", _fmt(community))
    if events:
        soul = _append_to_section(soul, "Notable Events", [str(e) for e in events])
    if voice:
        soul = _replace_section(soul, "Voice Notes", _fmt(voice))
    if builds:
        soul = _append_to_section(soul, "Build Log", [str(b) for b in builds])

    soul = _stamp(soul)

    try:
        SOUL_FILE.write_text(soul, encoding="utf-8")
        logger.info(
            "[soul] SOUL.md v%d written — beliefs:%d community:%d events:%d voice:%d builds:%d",
            version, len(evolving), len(community), len(events), len(voice), len(builds),
        )
    except Exception as e:
        logger.error("[soul] failed to write SOUL.md: %s", e)
        return False

    return True
