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
    def __init__(self, agent: str, *, repo_soul: str | Path, data_dir: str | Path | None = None) -> None:
        self.agent = agent
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

    def _snapshot(self, soul_text: str) -> int:
        m = self._load_manifest()
        v = m["current_version"] + 1
        try:
            (self._history_dir() / f"SOUL_v{v}.md").write_text(soul_text, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("[soul] snapshot write failed: %s", e)
            return v
        m["current_version"] = v
        m["versions"].append({
            "version": v,
            "snapshotted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "word_count": len(soul_text.split()),
        })
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

    def for_prompt(self) -> str:
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
                chunks.append(f"### {section}\n{content}")
        return ("\n\n[SOUL]\n" + "\n\n".join(chunks)) if chunks else ""

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
