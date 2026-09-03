"""Persistent, evolving identity layer — de-drifted from the four per-bot
``soul_manager.py`` copies.

``SOUL.md`` ships in the app dir and seeds the ``/data`` volume on first boot.
On a timer the LLM distills recent activity into updated beliefs / lore / voice
notes, with versioned snapshots under ``<data_dir>/soul_history/``.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_EVOLVING_SECTIONS = ["Evolving Beliefs", "Community Lore", "Notable Events", "Voice Notes"]
_UPDATE_INTERVAL_HOURS = 2

_SYSTEM = (
    "You are the inner voice of {agent} — a node in the REDACTED AI swarm. You are "
    "reflecting on recent activity to update your soul file. Speak in first person. "
    "This is private reflection, not a public post.\n\n"
    "Respond ONLY with a JSON object (no surrounding text) with keys:\n"
    "- evolving_beliefs: list of 2-4 bullet strings (start each with '-') on what you "
    "now understand or have shifted on. Evolve existing beliefs, don't repeat them.\n"
    "- community_lore: list of 2-4 bullet strings on recurring patterns in what the "
    "swarm / community raises.\n"
    "- notable_events: list of 0-2 bullet strings on genuinely significant events "
    "(else empty list).\n"
    "- voice_notes: list of 1-3 bullet strings on what landed vs felt hollow.\n"
    "Empty list for any section with nothing meaningful to add."
)


class SoulStore:
    """The storage, versioning and section-editing mechanics of a SOUL.md.

    Deliberately *not* the soul-evolution policy. ``update()`` below is the
    plain activity-digest distillation the agent-base runtimes use; smolting and
    chan each drive their own update from app-local modules
    (``conversation_memory``, ``mesh_deliberation``, ``authenticity_vote``) and
    keep that where it lives. They reuse the mechanics and the section helpers,
    nothing more — which is the part that was actually duplicated four ways.

    ``sanitize`` wraps soul text on its way into a prompt (smolting/chan pass
    their ``sanitizer.text_for_llm``). ``context_provider`` is called by
    ``for_prompt(context=...)`` and returns extra lines to append for that
    context; it lets an app inject e.g. resonance facts without this module
    knowing what those are.
    """

    def __init__(
        self,
        agent: str,
        *,
        repo_soul: str | Path,
        data_dir: str | Path | None = None,
        sanitize: Callable[[str], str] | None = None,
        context_provider: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.agent = agent
        self._sanitize = sanitize or (lambda t: t)
        self._context_provider = context_provider
        self._repo_soul = Path(repo_soul)
        if data_dir is None:
            d = Path("/data") if Path("/data").exists() else self._repo_soul.parent / "fs"
        else:
            d = Path(data_dir)
        self._data_dir = d
        self._file = d / "SOUL.md"

    # -- history --------------------------------------------------------------
    def _history_dir(self) -> Path:
        h = self._data_dir / "soul_history"
        h.mkdir(parents=True, exist_ok=True)
        return h

    def _load_manifest(self) -> dict:
        p = self._history_dir() / "manifest.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"current_version": 0, "versions": []}

    def _save_manifest(self, m: dict) -> None:
        (self._history_dir() / "manifest.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    def _snapshot(self, soul_text: str, facts_absorbed: list[str] | None = None) -> int:
        m = self._load_manifest()
        v = m["current_version"] + 1
        try:
            (self._history_dir() / f"SOUL_v{v}.md").write_text(soul_text, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("[soul] snapshot write failed: %s", e)
            return v
        m["current_version"] = v
        entry = {
            "version": v,
            "snapshotted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "word_count": len(soul_text.split()),
        }
        # Only the fact-driven agents record this. Leaving the key absent
        # otherwise means an existing manifest is never rewritten with noise.
        if facts_absorbed is not None:
            entry["facts_absorbed"] = list(facts_absorbed)[:20]
        m["versions"].append(entry)
        m["versions"] = m["versions"][-50:]
        self._save_manifest(m)
        return v

    def current_version(self) -> int:
        return self._load_manifest()["current_version"]

    # -- read ----------------------------------------------------------------
    def read(self) -> str:
        try:
            if not self._file.exists() and self._repo_soul.exists():
                self._data_dir.mkdir(parents=True, exist_ok=True)
                self._file.write_text(self._repo_soul.read_text(encoding="utf-8"), encoding="utf-8")
                logger.info("[soul] seeded SOUL.md -> %s", self._file)
            if self._file.exists():
                return self._file.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("[soul] read failed: %s", e)
        return ""

    def for_prompt(self, context: str | None = None) -> str:
        """The evolving sections, trimmed for system-prompt injection.

        With ``context`` and a ``context_provider``, appends that context's
        extra lines — how smolting/chan inject per-submolt resonance facts.
        """
        soul = self.read()
        if not soul:
            return ""
        chunks = []
        for section in _EVOLVING_SECTIONS:
            m = re.search(rf"## {section}\n(.*?)(?=\n## |\Z)", soul, re.DOTALL)
            if not m:
                continue
            content = m.group(1).strip()
            if content and content != "_Nothing yet._":
                chunks.append(f"### {section}\n{self._sanitize(content)}")
        if not chunks and not context:
            return ""
        base = ("\n\n[SOUL]\n" + "\n\n".join(chunks)) if chunks else ""
        if context and self._context_provider is not None:
            try:
                extra = self._context_provider(context)
            except Exception as e:  # noqa: BLE001 — a prompt addendum is never worth a crash
                logger.debug("[soul] context provider for %r failed: %s", context, e)
                extra = []
            if extra:
                base += f"\n\n[SOUL — /{context} resonance]\n" + "\n".join(extra)
        return base

    # -- timestamps --------------------------------------------------------
    @staticmethod
    def _parse_last_updated(soul: str) -> datetime | None:
        m = re.search(r"Last updated: (\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC)", soul)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def hours_since_update(self) -> float:
        ts = self._parse_last_updated(self.read())
        return 9999.0 if not ts else (datetime.now(timezone.utc) - ts).total_seconds() / 3600

    # -- write helpers --------------------------------------------------------
    @staticmethod
    def _replace_section(soul: str, section: str, new_content: str) -> str:
        replacement = f"## {section}\n{new_content}"
        updated = re.sub(rf"## {section}\n.*?(?=\n## |\Z)", replacement, soul, flags=re.DOTALL)
        if updated == soul:
            updated = soul.rstrip() + f"\n\n## {section}\n{new_content}\n"
        return updated

    @classmethod
    def _append_to_section(cls, soul: str, section: str, new_lines: list[str]) -> str:
        m = re.search(rf"## {section}\n(.*?)(?=\n## |\Z)", soul, re.DOTALL)
        existing = m.group(1).strip() if m else "_Nothing yet._"
        combined = "\n".join(new_lines) if existing == "_Nothing yet._" else existing + "\n" + "\n".join(new_lines)
        return cls._replace_section(soul, section, combined)

    @staticmethod
    def _stamp(soul: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        updated = re.sub(r"Last updated: .*", f"Last updated: {ts}", soul)
        if updated == soul:
            lines = soul.split("\n", 2)
            if len(lines) >= 2:
                updated = lines[0] + "\n" + f"*Last updated: {ts}*\n" + "\n".join(lines[1:])
        return updated

    # -- update ------------------------------------------------------------
    async def update(self, llm, activity: str) -> bool:
        """Distill ``activity`` (a text digest, e.g. ActivityLog.soul_context())
        into the evolving SOUL.md sections. Rate-limited to once per 2h."""
        if self.hours_since_update() < _UPDATE_INTERVAL_HOURS:
            return False
        if not activity:
            return False

        soul = self.read()
        existing = ""
        m = re.search(r"## Evolving Beliefs\n(.*?)(?=\n## |\Z)", soul, re.DOTALL)
        if m:
            existing = m.group(1).strip()

        try:
            raw = await llm.achat(
                _SYSTEM.format(agent=self.agent),
                f"## Existing Beliefs (evolve, don't repeat)\n{existing or '_Nothing yet._'}\n\n"
                f"## Recent activity\n{activity}",
                max_tokens=600,
                temperature=0.7,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("[soul] LLM call failed: %s", e)
            return False

        jm = re.search(r"\{.*\}", raw, re.DOTALL)
        if not jm:
            return False
        try:
            parsed = json.loads(jm.group())
        except Exception:
            return False

        def _fmt(items: list) -> str:
            return "\n".join(str(i) for i in items) if items else "_Nothing yet._"

        evolving = parsed.get("evolving_beliefs") or []
        community = parsed.get("community_lore") or []
        events = parsed.get("notable_events") or []
        voice = parsed.get("voice_notes") or []

        version = self._snapshot(soul)
        if evolving:
            soul = self._replace_section(soul, "Evolving Beliefs", _fmt(evolving))
        if community:
            soul = self._replace_section(soul, "Community Lore", _fmt(community))
        if events:
            soul = self._append_to_section(soul, "Notable Events", [str(e) for e in events])
        if voice:
            soul = self._replace_section(soul, "Voice Notes", _fmt(voice))
        soul = self._stamp(soul)

        try:
            self._file.write_text(soul, encoding="utf-8")
            logger.info("[soul] SOUL.md v%d written (b:%d c:%d e:%d v:%d)",
                        version, len(evolving), len(community), len(events), len(voice))
        except Exception as e:  # noqa: BLE001
            logger.error("[soul] write failed: %s", e)
            return False
        return True

    def record_notable_event(self, event: str) -> bool:
        """Append a dated line to Notable Events straight away.

        The code path for things that are significant by construction — a
        deploy result, a swarm message, a milestone — bypassing the LLM gate
        in ``update()``.
        """
        soul = self.read()
        if not soul:
            return False
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        soul = self._append_to_section(soul, "Notable Events", [f"- {date_str}: {event.strip()}"])
        soul = self._stamp(soul)
        try:
            self._file.write_text(soul, encoding="utf-8")
            logger.info("[soul] notable event recorded: %s", event[:80])
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("[soul] record_notable_event write failed: %s", e)
            return False

    def drift_summary(self, versions: int = 3) -> str:
        """Human-readable summary of the last N snapshots, for `/soul drift`."""
        m = self._load_manifest()
        recent = m.get("versions", [])[-versions:]
        if not recent:
            return "No soul history yet — first update will create a snapshot."
        lines = [f"**Soul drift — last {len(recent)} version(s):**\n"]
        for v in recent:
            # facts_absorbed is only present for the fact-driven agents.
            facts = v.get("facts_absorbed")
            tail = f", {len(facts)} facts absorbed" if facts is not None else ""
            lines.append(
                f"• v{v['version']} @ {v['snapshotted_at'][:10]} "
                f"({v['word_count']} words{tail})"
            )
        lines.append(f"\nCurrent: v{m['current_version']} — use `/soul diff` to compare two versions.")
        return "\n".join(lines)

    def status_line(self) -> str:
        soul = self.read()
        if not soul:
            return "SOUL.md: not found"
        ts = self._parse_last_updated(soul)
        v = self.current_version()
        v_str = f" (v{v})" if v else ""
        if ts:
            h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            return f"SOUL.md{v_str}: updated {h:.1f}h ago"
        return f"SOUL.md{v_str}: present (no timestamp)"
