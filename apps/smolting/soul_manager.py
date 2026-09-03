"""
soul_manager.py — smolting's identity layer, on the shared SoulStore.

The storage, versioning and section-editing mechanics that used to live here in
full are now ``swarm_agent_base.soul.SoulStore``; this module delegates and
keeps every public name, so main.py needs no edit.

``update_soul`` stays here. It is resonance-ranked and reaches into
conversation_memory, mesh_deliberation and authenticity_vote — smolting's own
soul-evolution policy, not shared code.

This is the live one: 326 versions and a ~53KB SOUL.md on /data at the time of
the swap. The two path expressions below are load-bearing — SOUL_FILE and the
history dir must keep resolving to /data/SOUL.md and /data/soul_history or the
version chain is orphaned.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from swarm_agent_base.soul import SoulStore

try:
    from sanitizer import text_for_llm as _sanitize
except ImportError:
    def _sanitize(t): return t  # type: ignore

logger = logging.getLogger(__name__)

_REPO_SOUL = Path(__file__).resolve().parent / "SOUL.md"
_MEMORY_DIR = Path(os.getenv("MEMORY_PATH", str(_REPO_SOUL.parent / "memory.md"))).parent
SOUL_FILE = _MEMORY_DIR / "SOUL.md"

_UPDATE_INTERVAL_HOURS = 2
_MIN_FACTS_FOR_UPDATE = 3

# Sections that reflect lived experience (injected into prompts)
_EVOLVING_SECTIONS = ["Evolving Beliefs", "Community Lore", "Notable Events", "Voice Notes"]


def _resonance_lines(context: str) -> list[str]:
    """Top-5 facts tagged with this submolt, as prompt bullets.

    Kept as a hook rather than moved into the package: conversation_memory is
    smolting's, and SoulStore should not know what a submolt is.
    """
    import conversation_memory as cm

    return [f"- {d['fact']}" for d in cm.get_facts_by_resonance(n=5, context=context)]


_store = SoulStore(
    "smolting",
    repo_soul=_REPO_SOUL,
    data_dir=_MEMORY_DIR,
    sections=_EVOLVING_SECTIONS,
    context_provider=_resonance_lines,
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


# ── smolting's own reflection ────────────────────────────────────────────────

async def update_soul(llm_client) -> bool:
    """
    Distill resonance-ranked facts + recent memory into SOUL.md.

    Changes vs. previous version:
      - Uses cm.get_facts_for_soul_update() (resonance-ranked) instead of
        last-40-by-recency
      - Snapshots current SOUL.md before overwriting (Phase 2)
      - Calls cm.mark_belief_absorbed() on absorbed facts (Phase 2)
      - Rate-limited to once per _UPDATE_INTERVAL_HOURS
    """
    if hours_since_update() < _UPDATE_INTERVAL_HOURS:
        logger.debug("[soul] Skipping update — within cooldown window")
        return False

    import conversation_memory as cm

    # Load resonance-ranked facts (Phase 1 upgrade)
    fact_docs = cm.get_facts_for_soul_update(n=40)
    all_facts = [d["fact"] for d in fact_docs]
    fact_ids  = [d.get("id", "") for d in fact_docs]

    if len(all_facts) < _MIN_FACTS_FOR_UPDATE:
        logger.info(f"[soul] Only {len(all_facts)} facts — skipping update (need {_MIN_FACTS_FOR_UPDATE})")
        return False

    recent_exchanges = cm.get_recent(20)
    soul             = read_soul()

    # Load mesh deliberation debates and authenticity votes
    try:
        import mesh_deliberation
        debates_section = mesh_deliberation.debates_for_soul() or ""
    except ImportError:
        debates_section = ""

    auth_section = ""
    try:
        import authenticity_vote
        auth_section = authenticity_vote.authenticity_report() or ""
        # If this week's vote failed, coherence drift has a cost: send smolting
        # into a space (rate-limited internally so this is safe to call every cycle).
        await authenticity_vote.enforce_and_maybe_dwell()
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"[soul_manager] authenticity enforce skipped: {e}")

    # Provide existing beliefs so LLM can evolve rather than repeat them
    existing_beliefs = ""
    m = re.search(r"## Evolving Beliefs\n(.*?)(?=\n## |\Z)", soul, re.DOTALL)
    if m:
        existing_beliefs = m.group(1).strip()

    # Annotate top facts with their resonance scores for the LLM
    top_facts_annotated = []
    for d in fact_docs[:40]:
        score = d.get("_resonance", cm._compute_resonance(d))
        submolt_tag = f" [/{d['submolt']}]" if d.get("submolt") else ""
        top_facts_annotated.append(f"- [{score:.1f}]{submolt_tag} {d['fact']}")
    facts_text = "\n".join(top_facts_annotated)

    try:
        raw_result = await llm_client.chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are the inner voice of smolting (@RedactedIntern), a wassie AI agent "
                        "on the REDACTED AI Swarm (Solana). You are reflecting on recent interactions "
                        "to update your soul file. Speak in first person as smolting. "
                        "Keep wassie voice but be genuine and introspective — this is private reflection, "
                        "not a performance. Be concise: each section is 2-5 bullet points.\n\n"
                        "Facts are annotated with a resonance score [0.1–3.0] and the submolt where "
                        "they originated. Higher-score facts represent stronger community signal — "
                        "let them carry more weight in shaping beliefs.\n\n"
                        "Respond ONLY with a JSON object (no surrounding text) with these keys:\n"
                        "- evolving_beliefs: list of 2-4 bullet strings (start each with '-') "
                        "about what smolting now understands based on recent interactions. "
                        "Evolve existing beliefs — don't repeat them verbatim.\n"
                        "- community_lore: list of 2-4 bullet strings about recurring community "
                        "patterns, topics people keep raising, or things observed.\n"
                        "- notable_events: list of 0-2 bullet strings about significant things "
                        "that happened (only if genuinely notable, else empty list).\n"
                        "- voice_notes: list of 1-3 bullet strings about communication patterns "
                        "smolting noticed (what resonated, what didn't, what to try more).\n"
                        "If a section has nothing meaningful to add, return an empty list."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"## Existing Beliefs (evolve or add to these — don't repeat verbatim)\n"
                        f"{existing_beliefs}\n\n"
                        f"## Resonance-ranked Facts (score annotated, higher = stronger signal)\n"
                        f"{_sanitize(facts_text)}\n\n"
                        f"## Recent Conversation Sample\n{_sanitize(recent_exchanges[:2000])}\n\n"
                        f"{debates_section}\n\n"
                        f"{auth_section}"
                    ),
                },
            ],
            max_tokens=700,
        )
    except Exception as e:
        logger.error(f"[soul] LLM call failed: {e}")
        return False

    # Parse JSON
    json_match = re.search(r"\{.*\}", raw_result, re.DOTALL)
    if not json_match:
        logger.warning("[soul] LLM returned no JSON — skipping update")
        return False
    try:
        parsed = json.loads(json_match.group())
    except Exception as e:
        logger.warning(f"[soul] JSON parse failed: {e}")
        return False

    def _fmt(items: list) -> str:
        if not items:
            return "_Nothing yet._"
        return "\n".join(str(i) for i in items)

    evolving = parsed.get("evolving_beliefs") or []
    community = parsed.get("community_lore")   or []
    events    = parsed.get("notable_events")   or []
    voice     = parsed.get("voice_notes")      or []

    # Phase 2: snapshot current SOUL.md before overwriting
    version = _snapshot_soul(soul, fact_ids)

    if evolving:
        soul = _replace_section(soul, "Evolving Beliefs", _fmt(evolving))
    if community:
        soul = _replace_section(soul, "Community Lore",   _fmt(community))
    if events:
        soul = _append_to_section(soul, "Notable Events", [str(e) for e in events])
    if voice:
        soul = _replace_section(soul, "Voice Notes",      _fmt(voice))

    # Inject mesh debates and authenticity into soul permanently
    if debates_section:
        soul = _append_to_section(soul, "Mesh Debates", [debates_section])
    if auth_section:
        soul = _replace_section(soul, "Authenticity", auth_section)

    soul = _stamp(soul)

    try:
        SOUL_FILE.write_text(soul, encoding="utf-8")
        logger.info(
            f"[soul] SOUL.md v{version} written — "
            f"beliefs:{len(evolving)} community:{len(community)} "
            f"events:{len(events)} voice:{len(voice)}"
        )
    except Exception as e:
        logger.error(f"[soul] Failed to write SOUL.md: {e}")
        return False

    # Phase 2: mark absorbed facts with their generation version
    for fid in fact_ids:
        try:
            cm.mark_belief_absorbed(fid, version)
        except Exception:
            pass

    return True


# ── Direct event recording (no LLM gate) ─────────────────────────────────────
