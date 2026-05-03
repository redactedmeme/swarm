# web_ui/skills_manager.py
"""
Agent Skills manager for the REDACTED terminal.

Skills conform to the agentskills.io specification:
  skill-name/
  ├── SKILL.md          Required: YAML frontmatter + instructions
  ├── scripts/          Optional: executable code
  ├── references/       Optional: reference docs
  └── assets/           Optional: static resources

Local skills are stored in {REPO_ROOT}/skills/.

Download sources:
  owner/repo                   → SKILL.md at repo root
  owner/repo/path/to/skill     → SKILL.md at that path
  https://github.com/...       → parsed automatically
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILLS_DIR.mkdir(exist_ok=True)

GITHUB_RAW = "https://raw.githubusercontent.com"
GITHUB_API = "https://api.github.com"

# GitHub token for higher API rate limits (optional)
_GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_GH_HEADERS = {"Accept": "application/vnd.github.v3+json"}
if _GH_TOKEN:
    _GH_HEADERS["Authorization"] = f"Bearer {_GH_TOKEN}"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _skill_dir(name: str) -> Path:
    return SKILLS_DIR / name


def _parse_source(source: str) -> tuple:
    """Parse source string → (owner, repo, branch, subpath)."""
    source = source.strip()
    # Strip full GitHub URL
    source = re.sub(r'^https?://github\.com/', '', source)
    # owner/repo/tree/branch/path
    m = re.match(r'^([^/]+)/([^/]+)/tree/([^/]+)(/.*)?$', source)
    if m:
        owner, repo, branch, path = m.groups()
        return owner, repo, branch, (path.lstrip('/') if path else '')
    # owner/repo[/path]
    parts = source.split('/', 2)
    owner = parts[0]
    repo  = parts[1] if len(parts) > 1 else ''
    path  = parts[2] if len(parts) > 2 else ''
    return owner, repo, 'main', path


def _fetch_raw(owner: str, repo: str, branch: str, filepath: str) -> Optional[str]:
    url = f"{GITHUB_RAW}/{owner}/{repo}/{branch}/{filepath}"
    try:
        r = requests.get(url, timeout=15, headers=_GH_HEADERS)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def _parse_frontmatter(content: str) -> dict:
    """Minimal YAML frontmatter parser (no PyYAML required)."""
    if not content.startswith('---'):
        return {}
    end = content.find('\n---', 3)
    if end == -1:
        return {}
    result = {}
    for line in content[3:end].splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _safe_name(raw: str) -> str:
    """Convert an arbitrary string to a valid skill name."""
    n = raw.lower()
    n = re.sub(r'[^a-z0-9]+', '-', n)
    n = n.strip('-')
    return n[:64] or 'unknown-skill'


def _fetch_subtree(owner: str, repo: str, branch: str, base: str, dest: Path):
    """Fetch scripts/, references/, assets/ from GitHub contents API."""
    for subdir in ('scripts', 'references', 'assets'):
        api_path = f"{base}/{subdir}" if base else subdir
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{api_path}"
        try:
            r = requests.get(url, timeout=10, headers=_GH_HEADERS)
            if r.status_code != 200:
                continue
            items = r.json()
            if not isinstance(items, list):
                continue
            (dest / subdir).mkdir(exist_ok=True)
            for item in items:
                if item.get('type') == 'file':
                    raw = _fetch_raw(owner, repo, branch, item['path'])
                    if raw is not None:
                        (dest / subdir / item['name']).write_text(raw, encoding='utf-8')
        except Exception:
            continue


# ── Public API ────────────────────────────────────────────────────────────────

def install(source: str) -> dict:
    """
    Download a skill from GitHub and install it locally.
    Returns {"ok": bool, "name": str, "message": str}
    """
    owner, repo, branch, path = _parse_source(source)
    if not owner or not repo:
        return {"ok": False, "name": "", "message": "invalid source — use: owner/repo or owner/repo/path/to/skill"}

    skill_md_rel = f"{path}/SKILL.md" if path else "SKILL.md"

    # Fetch SKILL.md (try main then master)
    content = _fetch_raw(owner, repo, branch, skill_md_rel)
    if content is None and branch == 'main':
        content = _fetch_raw(owner, repo, 'master', skill_md_rel)
        if content is not None:
            branch = 'master'

    if content is None:
        return {"ok": False, "name": "", "message": f"SKILL.md not found at {owner}/{repo}/{skill_md_rel}"}

    fm = _parse_frontmatter(content)
    name = fm.get('name') or _safe_name(path.split('/')[-1] if path else repo)

    # Create local skill directory
    skill_path = _skill_dir(name)
    skill_path.mkdir(parents=True, exist_ok=True)
    (skill_path / 'SKILL.md').write_text(content, encoding='utf-8')

    # Fetch optional subdirs
    _fetch_subtree(owner, repo, branch, path, skill_path)

    # Save provenance metadata
    meta = {"source": source, "owner": owner, "repo": repo, "branch": branch, "path": path}
    (skill_path / '.source.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')

    desc = fm.get('description', '(no description)')
    return {"ok": True, "name": name, "message": f"installed '{name}' — {desc[:100]}"}


def remove(name: str) -> dict:
    """Remove an installed skill by name."""
    skill_path = _skill_dir(name)
    if not skill_path.exists():
        return {"ok": False, "message": f"skill '{name}' not found"}
    shutil.rmtree(skill_path)
    return {"ok": True, "message": f"skill '{name}' removed"}


def list_skills() -> list:
    """Return metadata list for all installed skills."""
    result = []
    for d in sorted(SKILLS_DIR.iterdir()):
        skill_md = d / 'SKILL.md'
        if not d.is_dir() or not skill_md.exists():
            continue
        try:
            fm = _parse_frontmatter(skill_md.read_text(encoding='utf-8'))
            result.append({
                "name":        fm.get('name', d.name),
                "description": fm.get('description', ''),
                "compatibility": fm.get('compatibility', ''),
                "path":        str(d),
            })
        except Exception:
            continue
    return result


def get_skill(name: str) -> Optional[dict]:
    """Return full skill data for a named skill, or None if not found."""
    skill_path = _skill_dir(name)
    skill_md   = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return None
    content = skill_md.read_text(encoding='utf-8')
    fm = _parse_frontmatter(content)
    # List available extra files
    extras = []
    for sub in ('scripts', 'references', 'assets'):
        sub_path = skill_path / sub
        if sub_path.exists():
            extras.extend(f"{sub}/{f.name}" for f in sorted(sub_path.iterdir()) if f.is_file())
    return {
        "name":          fm.get('name', name),
        "description":   fm.get('description', ''),
        "compatibility": fm.get('compatibility', ''),
        "license":       fm.get('license', ''),
        "content":       content,
        "extras":        extras,
        "path":          str(skill_path),
    }


def skill_instructions(name: str) -> Optional[str]:
    """Return the SKILL.md body (post-frontmatter) for LLM injection."""
    skill = get_skill(name)
    if not skill:
        return None
    body = skill['content']
    if body.startswith('---'):
        end = body.find('\n---', 3)
        if end != -1:
            body = body[end + 4:].strip()
    return body


def to_prompt(active_names: list = None) -> str:
    """
    Generate <available_skills> XML for the LLM system prompt.
    Follows the agentskills.io recommended format.
    If active_names is None, lists all installed skills (metadata only).
    """
    skills = list_skills()
    if active_names is not None:
        skills = [s for s in skills if s['name'] in active_names]
    if not skills:
        return ""
    lines = ["<available_skills>"]
    for s in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{s['name']}</name>")
        lines.append(f"    <description>{s['description']}</description>")
        lines.append(f"    <location>{s['path']}/SKILL.md</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)
