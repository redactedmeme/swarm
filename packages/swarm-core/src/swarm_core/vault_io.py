# vault/vault_io.py
"""
Read/write API for the vault/ wiki.

Read  — search vault pages by keyword; read a specific page
Write — append a timestamped note to any vault page

Designed to be importable from smolting-telegram-bot (sys.path includes repo root).
"""
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from swarm_core.paths import vault_dir as _vault_dir
_VAULT_ROOT = _vault_dir()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _jst_now() -> str:
    jst = datetime.now(timezone.utc) + timedelta(hours=9)
    return jst.strftime("%Y-%m-%d %H:%M JST")


def _resolve_page(name: str) -> Optional[Path]:
    """
    Resolve a page name to an absolute path.
    Accepts:
      - exact relative path  : "agents/smolting.md"
      - stem only            : "smolting" → finds first match
      - section/stem         : "agents/smolting"
    """
    # Direct path
    direct = _VAULT_ROOT / name
    if direct.exists() and direct.suffix == ".md":
        return direct
    if direct.with_suffix(".md").exists():
        return direct.with_suffix(".md")

    # Fuzzy stem search
    stem = Path(name).stem.lower()
    for md in _VAULT_ROOT.rglob("*.md"):
        if md.stem.lower() == stem:
            return md

    # Partial match on stem
    for md in _VAULT_ROOT.rglob("*.md"):
        if stem in md.stem.lower():
            return md

    return None


# ── Read API ───────────────────────────────────────────────────────────────────

def list_pages() -> list[dict]:
    """Return all vault pages as [{section, name, path}, ...]."""
    pages = []
    for md in sorted(_VAULT_ROOT.rglob("*.md")):
        rel = md.relative_to(_VAULT_ROOT)
        parts = rel.parts
        section = parts[0] if len(parts) > 1 else "root"
        pages.append({
            "section": section,
            "name":    md.stem,
            "path":    str(rel),
            "abs":     str(md),
        })
    return pages


def read_page(name: str) -> Optional[str]:
    """Read a vault page by name or path. Returns markdown string or None."""
    path = _resolve_page(name)
    if not path:
        return None
    return path.read_text(encoding="utf-8")


def search_vault(query: str, max_results: int = 5) -> list[dict]:
    """
    Simple grep-style search across all vault .md files.
    Returns [{path, section, name, snippet}, ...] ranked by match count.
    """
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results = []

    for md in _VAULT_ROOT.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        matches = pattern.findall(text)
        if not matches:
            continue

        # Find first matching line for snippet
        snippet = ""
        for line in text.splitlines():
            if pattern.search(line):
                snippet = line.strip()[:160]
                break

        rel = md.relative_to(_VAULT_ROOT)
        parts = rel.parts
        results.append({
            "path":    str(rel),
            "section": parts[0] if len(parts) > 1 else "root",
            "name":    md.stem,
            "hits":    len(matches),
            "snippet": snippet,
        })

    results.sort(key=lambda r: r["hits"], reverse=True)
    return results[:max_results]


def get_index() -> str:
    """Return the vault index page."""
    idx = _VAULT_ROOT / "index.md"
    return idx.read_text(encoding="utf-8") if idx.exists() else "(vault index not found)"


# ── Write API ──────────────────────────────────────────────────────────────────

def append_note(page: str, note: str, author: str = "smolting") -> str:
    """
    Append a timestamped note to a vault page under a '## Notes' section.
    Creates the section if it doesn't exist.
    Returns the resolved page path string, or raises FileNotFoundError.
    """
    path = _resolve_page(page)
    if not path:
        raise FileNotFoundError(f"Vault page not found: {page!r}")

    text = path.read_text(encoding="utf-8")
    timestamp = _jst_now()
    entry = f"\n**{timestamp} — {author}:** {note.strip()}\n"

    if "## Notes" in text:
        text = text + entry
    else:
        text = text.rstrip() + "\n\n## Notes\n" + entry

    path.write_text(text, encoding="utf-8")
    return str(path.relative_to(_VAULT_ROOT))


def create_page(section: str, name: str, content: str) -> str:
    """
    Create a new vault page. section = 'agents' | 'architecture' | etc.
    Returns relative path string.
    """
    target_dir = _VAULT_ROOT / section
    target_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\-]", "-", name.lower()).strip("-")
    path = target_dir / f"{slug}.md"
    if path.exists():
        raise FileExistsError(f"Page already exists: {path.relative_to(_VAULT_ROOT)}")
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return str(path.relative_to(_VAULT_ROOT))


# ── Formatter (for Telegram) ───────────────────────────────────────────────────

def format_search_results(results: list[dict], query: str) -> str:
    if not results:
        return f"no vault pages matched '{query}'"
    lines = [f"vault search: `{query}`"]
    for r in results:
        lines.append(f"  [{r['section']}/{r['name']}]  {r['hits']} hit(s)")
        if r["snippet"]:
            lines.append(f"    › {r['snippet']}")
    return "\n".join(lines)


def format_page_preview(name: str, max_chars: int = 800) -> str:
    """Return a truncated preview of a vault page, safe for Telegram."""
    content = read_page(name)
    if not content:
        return f"vault page not found: `{name}`"
    preview = content[:max_chars]
    if len(content) > max_chars:
        preview += f"\n\n_(+{len(content) - max_chars} chars — use /vault read {name} for full page)_"
    return preview
