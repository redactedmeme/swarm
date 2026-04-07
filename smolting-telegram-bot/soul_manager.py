"""
soul_manager.py — persistent, evolving identity layer for smolting.

SOUL.md is committed to the repo and survives Railway redeploys.
Every 2 hours the LLM distills resonance-ranked facts + recent memory
into updated beliefs, community lore observations, and voice notes.

Phase 2 — Versioned snapshots:
  Before every write, the current SOUL.md is copied to
  /data/soul_history/SOUL_v{n}.md and a manifest is updated.
  This preserves the drift history — you can see how beliefs evolved.

Phase 3 — Submolt-contextual retrieval:
  get_soul_for_prompt(context="existential") injects the base SOUL.md
  sections PLUS the top resonance facts from that submolt, giving each
  post context-appropriate belief depth.
"""

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SOUL_FILE = Path(__file__).resolve().parent / "SOUL.md"

_UPDATE_INTERVAL_HOURS = 2
_MIN_FACTS_FOR_UPDATE  = 3

# Sections that reflect lived experience (injected into prompts)
_EVOLVING_SECTIONS = ["Evolving Beliefs", "Community Lore", "Notable Events", "Voice Notes"]


# ── History directory (Phase 2) ───────────────────────────────────────────────

def _history_dir() -> Path:
    """Return (and create) the soul history directory on the persistent volume."""
    base = Path(
        os.getenv("MEMORY_PATH", str(Path(__file__).resolve().parent / "memory.md"))
    ).parent
    d = base / "soul_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_manifest() -> dict:
    """Load the soul version manifest. Returns default if missing."""
    p = _history_dir() / "manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"current_version": 0, "versions": []}


def _save_manifest(manifest: dict) -> None:
    p = _history_dir() / "manifest.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _snapshot_soul(soul_text: str, facts_absorbed: list[str]) -> int:
    """
    Copy current SOUL.md to soul_history/SOUL_v{n}.md before overwriting.
    Updates the manifest and returns the new version number.
    """
    manifest = _load_manifest()
    version  = manifest["current_version"] + 1
    dest     = _history_dir() / f"SOUL_v{version}.md"
    try:
        dest.write_text(soul_text, encoding="utf-8")
    except Exception as e:
        logger.warning(f"[soul] Snapshot write failed: {e}")
        return version

    manifest["current_version"] = version
    manifest["versions"].append({
        "version":       version,
        "snapshotted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "facts_absorbed": facts_absorbed[:20],   # store first 20 fact IDs
        "word_count":    len(soul_text.split()),
    })
    # Keep manifest lean — only last 50 version entries
    manifest["versions"] = manifest["versions"][-50:]
    _save_manifest(manifest)
    logger.info(f"[soul] Snapshot → SOUL_v{version}.md ({len(soul_text.split())} words)")
    return version


def current_soul_version() -> int:
    return _load_manifest()["current_version"]


# ── Read ──────────────────────────────────────────────────────────────────────

def read_soul() -> str:
    """Return full SOUL.md content, or empty string if not found."""
    try:
        if SOUL_FILE.exists():
            return SOUL_FILE.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"[soul] read failed: {e}")
    return ""


def get_soul_for_prompt(context: str | None = None) -> str:
    """
    Return a trimmed block for system prompt injection.

    Phase 3 — Submolt context:
      If context (a submolt name) is provided, the base SOUL.md evolving
      sections are returned PLUS a 'Context resonance' addendum: the top-5
      resonance facts specifically tagged with that submolt.  This gives the
      LLM belief depth that was shaped by actual exchanges in that space.

    Parameters
    ----------
    context : submolt name e.g. 'existential', 'research', 'agentsouls'
              Pass None for the global/default behaviour.
    """
    soul = read_soul()
    if not soul:
        return ""

    chunks = []
    for section in _EVOLVING_SECTIONS:
        m = re.search(rf"## {section}\n(.*?)(?=\n## |\Z)", soul, re.DOTALL)
        if not m:
            continue
        content = m.group(1).strip()
        if content and content != "_Nothing yet._":
            chunks.append(f"### {section}\n{content}")

    if not chunks and not context:
        return ""

    base = "\n\n[SOUL]\n" + "\n\n".join(chunks) if chunks else ""

    # Phase 3: inject context-specific resonance facts
    if context:
        try:
            import conversation_memory as cm
            ctx_docs = cm.get_facts_by_resonance(n=5, context=context)
            if ctx_docs:
                lines = [f"- {d['fact']}" for d in ctx_docs]
                base += (
                    f"\n\n[SOUL — /{context} resonance]\n"
                    + "\n".join(lines)
                )
        except Exception as e:
            logger.debug(f"[soul] Context resonance inject failed: {e}")

    return base


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def _parse_last_updated(soul: str) -> datetime | None:
    m = re.search(r"Last updated: (\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC)", soul)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M UTC").replace(
                tzinfo=timezone.utc
            )
        except Exception:
            pass
    return None


def hours_since_update() -> float:
    """Hours since last soul update. Returns large number if never updated."""
    soul = read_soul()
    ts   = _parse_last_updated(soul) if soul else None
    if not ts:
        return 9999.0
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600


# ── Write helpers ─────────────────────────────────────────────────────────────

def _replace_section(soul: str, section: str, new_content: str) -> str:
    """Replace a section's body in the soul markdown."""
    replacement = f"## {section}\n{new_content}"
    updated = re.sub(
        rf"## {section}\n.*?(?=\n## |\Z)",
        replacement,
        soul,
        flags=re.DOTALL,
    )
    if updated == soul:
        # Section missing — append it
        updated = soul.rstrip() + f"\n\n## {section}\n{new_content}\n"
    return updated


def _append_to_section(soul: str, section: str, new_lines: list[str]) -> str:
    """Append lines to a section, replacing the _Nothing yet._ placeholder."""
    m = re.search(rf"## {section}\n(.*?)(?=\n## |\Z)", soul, re.DOTALL)
    existing = m.group(1).strip() if m else "_Nothing yet._"
    if existing == "_Nothing yet._":
        combined = "\n".join(new_lines)
    else:
        combined = existing + "\n" + "\n".join(new_lines)
    return _replace_section(soul, section, combined)


def _stamp(soul: str) -> str:
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    updated = re.sub(r"Last updated: .*", f"Last updated: {ts}", soul)
    if updated == soul:
        lines = soul.split("\n", 2)
        if len(lines) >= 2:
            updated = lines[0] + "\n" + f"*Last updated: {ts}*\n" + "\n".join(lines[1:])
    return updated


# ── Core update logic ─────────────────────────────────────────────────────────

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
                        f"{facts_text}\n\n"
                        f"## Recent Conversation Sample\n{recent_exchanges[:2000]}"
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


# ── Status helpers ────────────────────────────────────────────────────────────

def soul_status_line() -> str:
    """One-line status for /stats command."""
    soul = read_soul()
    if not soul:
        return "SOUL.md: not found"
    ts = _parse_last_updated(soul)
    version = current_soul_version()
    v_str   = f" (v{version})" if version else ""
    if ts:
        h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return f"SOUL.md{v_str}: updated {h:.1f}h ago"
    return f"SOUL.md{v_str}: present (no timestamp)"


def soul_drift_summary(versions: int = 3) -> str:
    """
    Return a human-readable summary of the last N soul versions for /soul drift.
    Lists version numbers, timestamps, word counts, and how many facts were absorbed.
    """
    manifest = _load_manifest()
    recent   = manifest.get("versions", [])[-versions:]
    if not recent:
        return "No soul history yet — first update will create a snapshot."

    lines = [f"**Soul drift — last {len(recent)} version(s):**\n"]
    for v in recent:
        lines.append(
            f"• v{v['version']} @ {v['snapshotted_at'][:10]} "
            f"({v['word_count']} words, "
            f"{len(v['facts_absorbed'])} facts absorbed)"
        )
    lines.append(
        f"\nCurrent: v{manifest['current_version']} — "
        f"use `/soul diff` to compare two versions."
    )
    return "\n".join(lines)
