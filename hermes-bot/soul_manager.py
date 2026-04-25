"""
soul_manager.py — persistent, evolving identity layer for patternbluelabs.

SOUL.md is committed to the repo and seeds the persistent Railway volume on
first boot. Every 2 hours the LLM distills recent activity (Moltbook posts,
group thoughts, Telegram replies, mesh debates) into updated beliefs,
community lore, and voice notes.

Versioned snapshots preserve drift history — you can see how the oracle's
understanding of Pattern Blue has evolved over time.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# SOUL.md lives on the persistent volume so it survives redeploys.
# Falls back to the repo SOUL.md for seeding on first run.
_REPO_SOUL  = Path(__file__).resolve().parent / "SOUL.md"
_DATA_DIR   = Path(os.getenv("ORACLE_STATE_DIR", "/data"))
SOUL_FILE   = _DATA_DIR / "SOUL.md"

_UPDATE_INTERVAL_HOURS = 2
_EVOLVING_SECTIONS = ["Evolving Beliefs", "Community Lore", "Notable Events", "Voice Notes"]


# ── Snapshot / manifest ───────────────────────────────────────────────────────

def _history_dir() -> Path:
    d = _DATA_DIR / "soul_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_manifest() -> dict:
    p = _history_dir() / "manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"current_version": 0, "versions": []}


def _save_manifest(manifest: dict) -> None:
    (_history_dir() / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _snapshot_soul(soul_text: str) -> int:
    manifest = _load_manifest()
    version  = manifest["current_version"] + 1
    dest     = _history_dir() / f"SOUL_v{version}.md"
    try:
        dest.write_text(soul_text, encoding="utf-8")
    except Exception as e:
        logger.warning("[soul] Snapshot write failed: %s", e)
        return version
    manifest["current_version"] = version
    manifest["versions"].append({
        "version":        version,
        "snapshotted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "word_count":     len(soul_text.split()),
    })
    manifest["versions"] = manifest["versions"][-50:]
    _save_manifest(manifest)
    logger.info("[soul] Snapshot → SOUL_v%d.md (%d words)", version, len(soul_text.split()))
    return version


def current_soul_version() -> int:
    return _load_manifest()["current_version"]


# ── Read ──────────────────────────────────────────────────────────────────────

def read_soul() -> str:
    """Return full SOUL.md. Seeds volume copy from repo on first run."""
    try:
        if not SOUL_FILE.exists() and _REPO_SOUL.exists():
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_REPO_SOUL, SOUL_FILE)
            logger.info("[soul] Seeded SOUL.md from repo → %s", SOUL_FILE)
        if SOUL_FILE.exists():
            return SOUL_FILE.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("[soul] read failed: %s", e)
    return ""


def get_soul_for_prompt() -> str:
    """
    Return the evolving sections as a trimmed block for system prompt injection.
    Only injects sections that have real content (not _Nothing yet._).
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

    if not chunks:
        return ""
    return "\n\n[SOUL]\n" + "\n\n".join(chunks)


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
    soul = read_soul()
    ts   = _parse_last_updated(soul) if soul else None
    if not ts:
        return 9999.0
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600


# ── Write helpers ─────────────────────────────────────────────────────────────

def _replace_section(soul: str, section: str, new_content: str) -> str:
    replacement = f"## {section}\n{new_content}"
    updated = re.sub(
        rf"## {section}\n.*?(?=\n## |\Z)",
        replacement,
        soul,
        flags=re.DOTALL,
    )
    if updated == soul:
        updated = soul.rstrip() + f"\n\n## {section}\n{new_content}\n"
    return updated


def _append_to_section(soul: str, section: str, new_lines: list[str]) -> str:
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
        import swarm_inbox
        # Read any completed thought exchanges for soul reflection
        recent = om.get_recent(n=20, kind="mesh_debate")
        if recent:
            debates_section = "## Recent mesh debates\n" + "\n".join(
                f"- {r['title']}" for r in recent
            )
    except Exception:
        pass

    try:
        raw_result = await llm_client.chat_completion(
            [
                {
                    "role": "system",
                    "content": (
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
                },
                {
                    "role": "user",
                    "content": (
                        f"## Existing Beliefs (evolve or add to — don't repeat verbatim)\n"
                        f"{existing_beliefs or '_Nothing yet._'}\n\n"
                        f"## Recent activity\n{activity}\n\n"
                        f"{debates_section}"
                    ).strip(),
                },
            ],
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


# ── Direct event recording (no LLM gate) ─────────────────────────────────────

def record_notable_event(event: str) -> bool:
    """Immediately append a dated event to Notable Events, bypassing the LLM gate."""
    soul = read_soul()
    if not soul:
        return False
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    soul = _append_to_section(soul, "Notable Events", [f"- {date_str}: {event.strip()}"])
    soul = _stamp(soul)
    try:
        SOUL_FILE.write_text(soul, encoding="utf-8")
        logger.info("[soul] Notable event recorded: %s", event[:80])
        return True
    except Exception as e:
        logger.error("[soul] record_notable_event failed: %s", e)
        return False


# ── Status ────────────────────────────────────────────────────────────────────

def soul_status_line() -> str:
    soul = read_soul()
    if not soul:
        return "SOUL.md: not found"
    ts      = _parse_last_updated(soul)
    version = current_soul_version()
    v_str   = f" (v{version})" if version else ""
    if ts:
        h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return f"SOUL.md{v_str}: updated {h:.1f}h ago"
    return f"SOUL.md{v_str}: present (no timestamp)"
