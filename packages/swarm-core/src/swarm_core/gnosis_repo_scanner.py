#!/usr/bin/env python3
"""
python/gnosis_repo_scanner.py
GnosisAccelerator — Repository Introspection Engine

Walks the swarm repo, extracts structured knowledge about every agent,
node, space, python script, and doc file, detects deltas since the last
scan, and writes discoveries to mem0 under agent_id="gnosis".

Usage (standalone):
    python python/gnosis_repo_scanner.py
    python python/gnosis_repo_scanner.py --dry-run
    python python/gnosis_repo_scanner.py --force   # rescan everything
    python python/gnosis_repo_scanner.py --stats

Called by gnosis_accelerator.py as part of each daemon cycle.
Returns a list of discovery strings for the orchestrator to log.
"""

import os
import sys
import json
import time
import argparse
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Paths ──────────────────────────────────────────────────────────────────────
from swarm_core.paths import repo_root as _repo_root, mem0_dir as _mem0_dir
_ROOT  = _repo_root()
_MEM0  = _mem0_dir()
_INDEX = _ROOT / "fs" / "gnosis_repo_index.json"

if str(_MEM0) not in sys.path:
    sys.path.insert(0, str(_MEM0))

_env = _ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        for _l in _env.read_text(encoding="utf-8").splitlines():
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                k, _, v = _l.partition("=")
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

GNOSIS_AGENT_ID = "gnosis"

# ── Scan targets ───────────────────────────────────────────────────────────────
SCAN_TARGETS: List[Tuple[str, str, str]] = [
    # (label, glob_pattern, file_suffix_filter)
    ("agent",   "agents/*.character.json",  ".json"),
    ("node",    "nodes/*.character.json",   ".json"),
    ("space",   "spaces/*.space.json",      ".json"),
    ("python",  "python/*.py",              ".py"),
    ("doc",     "docs/*.md",                ".md"),
]

# Fields to extract per file type for the fingerprint
def _fingerprint(path: Path) -> str:
    stat = path.stat()
    content_hash = hashlib.md5(
        path.read_bytes()[:4096]  # first 4KB is enough for change detection
    ).hexdigest()[:12]
    return f"{stat.st_size}:{content_hash}"


def _summarize_json(path: Path, label: str) -> str:
    """Extract a one-line description from a character/space JSON."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        name = data.get("name") or path.stem
        desc = (
            data.get("description")
            or data.get("role")
            or data.get("persona", {}).get("voice", "")
            or ""
        )
        # Truncate
        desc = desc[:200].replace("\n", " ").strip()
        tier = data.get("tier", "")
        dim  = data.get("pattern_blue_dimension", "")
        tools_count = len(data.get("tools", []))
        parts = [f"{label} '{name}'"]
        if tier:   parts.append(f"tier={tier}")
        if dim:    parts.append(f"dimension={dim}")
        if tools_count: parts.append(f"tools={tools_count}")
        if desc:   parts.append(f"— {desc}")
        return " ".join(parts)
    except Exception:
        return f"{label} '{path.stem}' (parse error)"


def _summarize_py(path: Path) -> str:
    """Extract module docstring from a Python file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        # Find first docstring
        in_docstring = False
        doc_lines = []
        for line in lines[:30]:
            stripped = line.strip()
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    in_docstring = True
                    rest = stripped[3:]
                    if rest.endswith('"""') or rest.endswith("'''"):
                        return f"python '{path.name}' — {rest[:-3].strip()}"
                    if rest:
                        doc_lines.append(rest)
            else:
                if stripped.endswith('"""') or stripped.endswith("'''"):
                    doc_lines.append(stripped[:-3])
                    break
                doc_lines.append(stripped)
        if doc_lines:
            return f"python '{path.name}' — {' '.join(doc_lines[:2])[:180]}"
        # Fall back to first comment
        for line in lines[:5]:
            if line.strip().startswith("#") and len(line.strip()) > 10:
                return f"python '{path.name}' — {line.strip()[1:].strip()[:180]}"
        return f"python '{path.name}' ({path.stat().st_size} bytes)"
    except Exception:
        return f"python '{path.name}' (read error)"


def _summarize_md(path: Path) -> str:
    """Extract title + first sentence from a markdown doc."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        title = next((l.lstrip("#").strip() for l in lines if l.startswith("#")), path.stem)
        # First non-heading line of substance
        body = next((l for l in lines if l and not l.startswith("#") and len(l) > 20), "")
        body = body[:180]
        return f"doc '{title}' — {body}" if body else f"doc '{title}'"
    except Exception:
        return f"doc '{path.stem}' (read error)"


# ── Index ──────────────────────────────────────────────────────────────────────

def _load_index() -> Dict[str, str]:
    try:
        if _INDEX.exists():
            return json.loads(_INDEX.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_index(index: Dict[str, str]) -> None:
    _INDEX.parent.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(index, indent=2), encoding="utf-8")


# ── Scanner ────────────────────────────────────────────────────────────────────

def scan(
    dry_run: bool = False,
    force:   bool = False,
) -> List[str]:
    """
    Scan the repo, write discoveries to mem0, return list of discovery strings.
    """
    mem0_available = False
    _mem0_mod = None
    if not dry_run:
        try:
            import mem0_wrapper as _m
            if _m.is_available():
                _mem0_mod = _m
                mem0_available = True
            else:
                print("[gnosis_repo_scanner] mem0 unavailable — discoveries printed only")
        except ImportError:
            print("[gnosis_repo_scanner] mem0_wrapper not found")

    index = {} if force else _load_index()
    discoveries: List[str] = []
    new_count = 0
    changed_count = 0
    unchanged_count = 0

    scan_time = time.time()

    for label, pattern, _ in SCAN_TARGETS:
        found = sorted(_ROOT.glob(pattern))
        for path in found:
            key = str(path.relative_to(_ROOT))
            fp  = _fingerprint(path)

            # Generate human-readable summary
            if label in ("agent", "node", "space"):
                summary = _summarize_json(path, label)
            elif label == "python":
                summary = _summarize_py(path)
            else:
                summary = _summarize_md(path)

            if key not in index:
                status = "NEW"
                new_count += 1
            elif index[key] != fp:
                status = "CHANGED"
                changed_count += 1
            else:
                unchanged_count += 1
                continue  # skip — no change

            discovery = f"[GNOSIS repo {status}] {summary}"
            discoveries.append(discovery)

            if dry_run:
                print(f"  [dry] {status:<8} {key}")
                index[key] = fp  # track in dry mode for display
                continue

            # Write to mem0
            if mem0_available and _mem0_mod:
                result = _mem0_mod.add_memory(
                    discovery,
                    agent_id=GNOSIS_AGENT_ID,
                    metadata={
                        "type":      "repo_scan",
                        "status":    status,
                        "label":     label,
                        "file":      key,
                        "scan_time": scan_time,
                    },
                )
                if result.get("status") == "ok":
                    index[key] = fp
                    print(f"  [{status:<8}] {key}")
                else:
                    print(f"  [err]     {key}: {result.get('message')}")
            else:
                index[key] = fp
                print(f"  [{status:<8}] {key}  (mem0 unavailable — indexed only)")

    # ── Cross-reference synthesis ──────────────────────────────────────────────
    # Build a compact relationship map for the swarm manifest
    all_agents  = [p.stem for p in _ROOT.glob("agents/*.character.json")]
    all_nodes   = [p.stem for p in _ROOT.glob("nodes/*.character.json")]
    all_spaces  = [p.stem.replace(".space", "") for p in _ROOT.glob("spaces/*.space.json")]
    all_python  = [p.name for p in _ROOT.glob("python/*.py") if not p.name.startswith("_")]
    all_docs    = [p.stem for p in _ROOT.glob("docs/*.md")]

    manifest = (
        f"[GNOSIS repo manifest @ {time.strftime('%Y-%m-%d %H:%M')}] "
        f"agents={len(all_agents)} nodes={len(all_nodes)} spaces={len(all_spaces)} "
        f"python={len(all_python)} docs={len(all_docs)} | "
        f"agents: {', '.join(all_agents[:8])}{'...' if len(all_agents)>8 else ''} | "
        f"nodes: {', '.join(all_nodes)} | "
        f"spaces: {', '.join(all_spaces)} | "
        f"python: {', '.join(all_python[:10])}{'...' if len(all_python)>10 else ''}"
    )
    discoveries.append(manifest)

    manifest_key = f"manifest:{time.strftime('%Y-%m-%d')}"
    if manifest_key not in index or force:
        if not dry_run and mem0_available and _mem0_mod:
            result = _mem0_mod.add_memory(
                manifest,
                agent_id=GNOSIS_AGENT_ID,
                metadata={"type": "repo_manifest", "scan_time": scan_time},
            )
            if result.get("status") == "ok":
                index[manifest_key] = str(scan_time)
        print(f"\n  [manifest] {manifest[:120]}...")

    if not dry_run:
        _save_index(index)

    print(
        f"\n[gnosis_repo_scanner] scan complete — "
        f"{new_count} new, {changed_count} changed, {unchanged_count} unchanged"
    )
    return discoveries


def stats() -> None:
    index = _load_index()
    if not index:
        print("[gnosis_repo_scanner] no index yet — run scanner first")
        return
    by_type: Dict[str, int] = {}
    for key in index:
        ext = Path(key).suffix or "other"
        by_type[ext] = by_type.get(ext, 0) + 1
    print(f"[gnosis_repo_scanner] index: {len(index)} files tracked")
    for ext, count in sorted(by_type.items()):
        print(f"  {ext:<12} {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GnosisAccelerator — repo introspection")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force",   action="store_true")
    parser.add_argument("--stats",   action="store_true")
    args = parser.parse_args()
    if args.stats:
        stats()
    else:
        results = scan(dry_run=args.dry_run, force=args.force)
        print(f"\n  {len(results)} discovery entries generated")
