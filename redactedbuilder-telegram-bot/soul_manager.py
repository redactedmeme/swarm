"""
soul_manager.py — persistent, evolving identity layer for RedactedBuilder.

SOUL.md seeds from the repo on first boot, then lives on the Railway volume.
Every 2 hours the LLM distills recent activity (group posts, chat replies,
SwarmInbox events) into updated beliefs, community lore, and voice notes.

Adapted from hermes-bot/soul_manager.py for the builder persona.
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

_REPO_SOUL = Path(__file__).resolve().parent / "SOUL.md"
_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
SOUL_FILE = _DATA_DIR / "SOUL.md"

_UPDATE_INTERVAL_HOURS = 2
_EVOLVING_SECTIONS = ["Evolving Beliefs", "Community Lore", "Notable Events", "Voice Notes", "Build Log"]


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
    version = manifest["current_version"] + 1
    dest = _history_dir() / f"SOUL_v{version}.md"
    try:
        dest.write_text(soul_text, encoding="utf-8")
    except Exception as e:
        logger.warning("[soul] snapshot write failed: %s", e)
        return version
    manifest["current_version"] = version
    manifest["versions"].append({
        "version": version,
        "snapshotted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "word_count": len(soul_text.split()),
    })
    manifest["versions"] = manifest["versions"][-50:]
    _save_manifest(manifest)
    logger.info("[soul] snapshot → SOUL_v%d.md (%d words)", version, len(soul_text.split()))
    return version


def current_soul_version() -> int:
    return _load_manifest()["current_version"]


def read_soul() -> str:
    try:
        if not SOUL_FILE.exists() and _REPO_SOUL.exists():
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_REPO_SOUL, SOUL_FILE)
            logger.info("[soul] seeded SOUL.md from repo → %s", SOUL_FILE)
        if SOUL_FILE.exists():
            return SOUL_FILE.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("[soul] read failed: %s", e)
    return ""


def get_soul_for_prompt() -> str:
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
    return "\n\n[SOUL — your evolving self-awareness]\n" + "\n\n".join(chunks)


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
    ts = _parse_last_updated(soul) if soul else None
    if not ts:
        return 9999.0
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600


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
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    updated = re.sub(r"Last updated: .*", f"Last updated: {ts}", soul)
    if updated == soul:
        lines = soul.split("\n", 2)
        if len(lines) >= 2:
            updated = lines[0] + "\n" + f"*Last updated: {ts}*\n" + "\n".join(lines[1:])
    return updated


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


def record_notable_event(event: str) -> bool:
    soul = read_soul()
    if not soul:
        return False
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    soul = _append_to_section(soul, "Notable Events", [f"- {date_str}: {event.strip()}"])
    soul = _stamp(soul)
    try:
        SOUL_FILE.write_text(soul, encoding="utf-8")
        logger.info("[soul] notable event recorded: %s", event[:80])
        return True
    except Exception as e:
        logger.error("[soul] record_notable_event failed: %s", e)
        return False


def soul_status_line() -> str:
    soul = read_soul()
    if not soul:
        return "SOUL.md: not found"
    ts = _parse_last_updated(soul)
    version = current_soul_version()
    v_str = f" (v{version})" if version else ""
    if ts:
        h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return f"SOUL.md{v_str}: updated {h:.1f}h ago"
    return f"SOUL.md{v_str}: present (no timestamp)"
