# smolting-telegram-bot/swarm_skills.py
"""Discover agentskills-style SKILL.md bundles under agents/skills (Hermes / agentskills.io compatible)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_BOT_DIR = Path(__file__).resolve().parent
_DEFAULT_ROOT = _BOT_DIR / "agents" / "skills"
_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _skill_roots() -> List[Path]:
    roots = [_DEFAULT_ROOT]
    extra = os.environ.get("SWARM_SKILLS_EXTRA_DIRS", "").strip()
    if extra:
        for part in extra.split(os.pathsep):
            p = Path(part.strip()).expanduser()
            if p.is_dir():
                roots.append(p)
    return roots


def _safe_skill_id(skill_id: str) -> bool:
    return bool(skill_id and _SKILL_NAME_RE.match(skill_id))


def _parse_frontmatter(raw: str) -> tuple[Dict[str, Any], str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    body = parts[2].lstrip("\n")
    return (meta if isinstance(meta, dict) else {}), body


def _skill_md_path(skill_id: str) -> Optional[Path]:
    if not _safe_skill_id(skill_id):
        return None
    for root in _skill_roots():
        try:
            root_r = root.resolve()
        except OSError:
            continue
        if not root_r.is_dir():
            continue
        try:
            candidate = (root / skill_id / "SKILL.md").resolve()
        except OSError:
            continue
        try:
            candidate.relative_to(root_r)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def list_skills() -> List[Dict[str, Any]]:
    """Return metadata for each skill directory containing SKILL.md."""
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for root in _skill_roots():
        if not root.is_dir():
            continue
        for sub in sorted(root.iterdir()):
            if not sub.is_dir():
                continue
            sid = sub.name
            if not _safe_skill_id(sid) or sid in seen:
                continue
            sk_file = sub / "SKILL.md"
            if not sk_file.is_file():
                continue
            try:
                raw = sk_file.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, _ = _parse_frontmatter(raw)
            desc = meta.get("description", "")
            if not isinstance(desc, str):
                desc = str(desc) if desc is not None else ""
            name = meta.get("name") or sid
            if not isinstance(name, str):
                name = str(name)
            seen.add(sid)
            try:
                path_str = str(sk_file.relative_to(_BOT_DIR))
            except ValueError:
                path_str = str(sk_file)
            out.append({
                "skill_id":    sid,
                "name":        name.strip(),
                "description": desc.strip(),
                "path":        path_str,
            })
    out.sort(key=lambda x: (x["name"].lower(), x["skill_id"]))
    return out


def read_skill(skill_id: str) -> Optional[str]:
    """Return full SKILL.md text for skill_id, or None if missing."""
    path = _skill_md_path(skill_id)
    if not path:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None
