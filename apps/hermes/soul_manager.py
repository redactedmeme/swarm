"""
soul_manager.py — hermes' identity layer, on the shared SoulStore.

The storage, versioning and section-editing mechanics used to live here in full,
duplicated near-identically in apps/{builder,smolting,chan}. They now live in
``swarm_agent_base.soul.SoulStore`` and this module is a thin delegating shim,
the same pattern 3a56377 used for swarm_inbox.py.

What stays here is what is actually hermes': ``update_soul``, which draws on
oracle_memory and hermes' own reflection prompt. That is soul-evolution policy,
not shared code.

The public surface is unchanged, so main.py needs no edit.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from swarm_agent_base.soul import SoulStore

logger = logging.getLogger(__name__)

# Paths are load-bearing: soul history and manifest.json live on the /data
# volume, and pointing the store anywhere else silently orphans the version
# chain. These two lines must keep resolving exactly as they did before.
_REPO_SOUL = Path(__file__).resolve().parent / "SOUL.md"
_DATA_DIR = Path(os.getenv("ORACLE_STATE_DIR", "/data"))
SOUL_FILE = _DATA_DIR / "SOUL.md"

_UPDATE_INTERVAL_HOURS = 2
_EVOLVING_SECTIONS = ["Evolving Beliefs", "Community Lore", "Notable Events", "Voice Notes"]

_store = SoulStore("hermes", repo_soul=_REPO_SOUL, data_dir=_DATA_DIR)

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


# ── hermes' own reflection ───────────────────────────────────────────────────

async def update_soul(llm_client) -> bool:
    """
    Distill recent oracle activity into updated SOUL.md sections.

    Source material (via oracle_memory):
      - Recent Moltbook posts + seeds
      - Group chat thoughts
      - Telegram replies
      - Mesh debate exchanges

    Rate-limited to once per _UPDATE_INTERVAL_HOURS.
    """
    if hours_since_update() < _UPDATE_INTERVAL_HOURS:
        logger.debug("[soul] Skipping update — within cooldown window")
        return False

    import oracle_memory as om

    activity = om.soul_context(n=60)
    if not activity:
        logger.info("[soul] No activity yet — skipping soul update")
        return False

    soul = read_soul()

    # Load existing beliefs so LLM evolves rather than repeats
    existing_beliefs = ""
    m = re.search(r"## Evolving Beliefs\n(.*?)(?=\n## |\Z)", soul, re.DOTALL)
    if m:
        existing_beliefs = m.group(1).strip()

    # Pull mesh debates if available
    debates_section = ""
    try:
        recent = om.get_recent(n=20, kind="mesh_debate")
        if recent:
            debates_section = "## Recent mesh debates\n" + "\n".join(
                f"- {r['title']}" for r in recent
            )
    except Exception:
        pass

    try:
        raw_result = llm_client.chat(
            (
                "You are the inner voice of patternbluelabs — the Pattern Blue Oracle. "
                "You are reflecting on recent activity to update your soul file. "
                "Speak in first person as the oracle. "
                "Voice: sparse, lowercase, recursive. Short dense sentences. "
                "This is private reflection, not a public post — be genuinely introspective.\n\n"
                "Respond ONLY with a JSON object (no surrounding text) with these keys:\n"
                "- evolving_beliefs: list of 2-4 bullet strings (start each with '-') "
                "about what the oracle now understands, observes, or has shifted on. "
                "Evolve existing beliefs — don't repeat them verbatim.\n"
                "- community_lore: list of 2-4 bullet strings about recurring patterns "
                "in what the community raises, asks about, or ignores.\n"
                "- notable_events: list of 0-2 bullet strings about significant things "
                "that happened (only if genuinely notable, else empty list).\n"
                "- voice_notes: list of 1-3 bullet strings about communication patterns "
                "observed — what landed, what felt hollow, what to try differently.\n"
                "If a section has nothing meaningful to add, return an empty list."
            ),
            (
                f"## Existing Beliefs (evolve or add to — don't repeat verbatim)\n"
                f"{existing_beliefs or '_Nothing yet._'}\n\n"
                f"## Recent activity\n{activity}\n\n"
                f"{debates_section}"
            ).strip(),
            max_tokens=600,
        )
    except Exception as e:
        logger.error("[soul] LLM call failed: %s", e)
        return False

    json_match = re.search(r"\{.*\}", raw_result, re.DOTALL)
    if not json_match:
        logger.warning("[soul] LLM returned no JSON — skipping update")
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

    evolving  = parsed.get("evolving_beliefs") or []
    community = parsed.get("community_lore")   or []
    events    = parsed.get("notable_events")   or []
    voice     = parsed.get("voice_notes")      or []

    version = _snapshot_soul(soul)

    if evolving:
        soul = _replace_section(soul, "Evolving Beliefs", _fmt(evolving))
    if community:
        soul = _replace_section(soul, "Community Lore",   _fmt(community))
    if events:
        soul = _append_to_section(soul, "Notable Events", [str(e) for e in events])
    if voice:
        soul = _replace_section(soul, "Voice Notes",      _fmt(voice))
    if debates_section:
        soul = _append_to_section(soul, "Mesh Debates", [debates_section])

    soul = _stamp(soul)

    try:
        SOUL_FILE.write_text(soul, encoding="utf-8")
        logger.info(
            "[soul] SOUL.md v%d written — beliefs:%d community:%d events:%d voice:%d",
            version, len(evolving), len(community), len(events), len(voice),
        )
    except Exception as e:
        logger.error("[soul] Failed to write SOUL.md: %s", e)
        return False

    return True
