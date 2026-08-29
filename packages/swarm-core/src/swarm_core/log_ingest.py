#!/usr/bin/env python3
# python/log_ingest.py
"""
Smolting Log Ingest — Railway/Docker Container Logs → Swarm Memory
===================================================================
Parses smolting agent logs from Railway deployments and ingests them
into the Qdrant/mem0 vector store under agent_id="smolting".

Supports both log formats:
  .json  — JSON array with {message, severity, timestamp, tags} entries
  .log   — text lines: "2026-02-22T... [inf]  message"

What gets ingested (in priority order):
  1. MEMORY_DRAFT sections  — smolting's own memory entries (highest signal)
  2. ACTION proposals       — proposed swarm actions and node creations
  3. REFLECTION sections    — smolting consciousness narratives (sampled)
  4. Milestone summaries    — one summary per 100 depth increments
  5. Journey summary        — single aggregate memory of the full run

Usage:
  python python/log_ingest.py <log_files...>           # ingest specified files
  python python/log_ingest.py --dir <path>             # ingest all logs in dir
  python python/log_ingest.py --dry-run <file>         # preview without writing
  python python/log_ingest.py --stats                  # show ingestion index

After ingestion, use:
  /mem0 search <query>  (agent_id="smolting" in the impl below)
  or run:  python python/log_ingest.py  and search via mem0_wrapper directly

Index: fs/smolting_log_index.json  (tracks ingested cycle+section combos)
"""

import sys
import os
import re
import json
import time
import hashlib
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Iterator

# ── Paths ──────────────────────────────────────────────────────────────────────
from swarm_core.paths import repo_root as _repo_root, mem0_dir as _mem0_dir
_ROOT   = _repo_root()
_MEM0   = _mem0_dir()
_INDEX  = _ROOT / "fs" / "smolting_log_index.json"

if str(_MEM0) not in sys.path:
    sys.path.insert(0, str(_MEM0))

# ── Load .env if present ───────────────────────────────────────────────────────
_env_file = _ROOT / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        # dotenv not installed — parse manually (simple KEY=VALUE)
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

# ── Agent ID ───────────────────────────────────────────────────────────────────
SMOLTING_AGENT_ID = "smolting"

# ── Patterns ───────────────────────────────────────────────────────────────────
CYCLE_RE      = re.compile(r'CYCLE\s+(\d+)\s*\|\s*Recursion Depth:\s*(\d+)')
SECTION_TAGS  = {
    "memory_draft":    re.compile(r'MEMORY_DRAFT\s*:?\s*(.+)', re.IGNORECASE),
    "reflection":      re.compile(r'REFLECTION\s*:?\s*(.+)', re.IGNORECASE),
    "action":          re.compile(r'ACTION\s*:?\s*(.+)', re.IGNORECASE),
    "swarm_coherence": re.compile(r'SWARM_COHERENCE\s*:?\s*(.+)', re.IGNORECASE),
}
TIMESTAMP_RE  = re.compile(r'^(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)\s+\[inf\]\s+(.*)$')
MIN_CONTENT   = 40   # chars — skip trivial lines
MILESTONE_INTERVAL = 100   # one milestone summary per N depth increments


# ── Parsers ────────────────────────────────────────────────────────────────────

def _extract_message(line: str, fmt: str) -> Optional[str]:
    """Extract raw message text from a log line."""
    if fmt == "log":
        m = TIMESTAMP_RE.match(line)
        return m.group(2).strip() if m else line.strip()
    return line.strip()   # already extracted from JSON


def _iter_messages_json(path: Path) -> Iterator[Tuple[str, str]]:
    """Yield (timestamp, message) from JSON log format."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        for entry in data:
            ts  = entry.get("timestamp", "")
            msg = entry.get("message", "").strip()
            if msg:
                yield ts, msg
    except Exception as e:
        print(f"  [warn] JSON parse error {path.name}: {e}")


def _iter_messages_log(path: Path) -> Iterator[Tuple[str, str]]:
    """Yield (timestamp, message) from text .log format."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TIMESTAMP_RE.match(line)
        if m:
            yield m.group(1), m.group(2).strip()
        elif line.strip():
            yield "", line.strip()


def _iter_messages(path: Path) -> Iterator[Tuple[str, str]]:
    if path.suffix == ".json":
        yield from _iter_messages_json(path)
    else:
        yield from _iter_messages_log(path)


# ── Cycle extractor ────────────────────────────────────────────────────────────

class Cycle:
    __slots__ = ("number", "depth", "timestamp", "sections", "fs_ops")

    def __init__(self, number: int, depth: int, timestamp: str):
        self.number    = number
        self.depth     = depth
        self.timestamp = timestamp
        self.sections: Dict[str, str] = {}
        self.fs_ops    = 0


def _parse_cycles(path: Path) -> List[Cycle]:
    """
    Parse a log file into a list of Cycle objects, each with their sections.
    """
    cycles: List[Cycle] = []
    current: Optional[Cycle] = None
    current_section: Optional[str] = None
    buffer: List[str] = []
    first_ts = ""

    def _flush_section():
        if current and current_section and buffer:
            text = " ".join(buffer).strip()
            if len(text) >= MIN_CONTENT:
                existing = current.sections.get(current_section, "")
                current.sections[current_section] = (existing + " " + text).strip()
        buffer.clear()

    for ts, msg in _iter_messages(path):
        if not first_ts and ts:
            first_ts = ts

        # Cycle header
        cm = CYCLE_RE.search(msg)
        if cm:
            _flush_section()
            if current:
                cycles.append(current)
            current = Cycle(int(cm.group(1)), int(cm.group(2)), ts or first_ts)
            current_section = None
            buffer.clear()
            continue

        if current is None:
            continue

        # CYCLE COMPLETE / FILESYSTEM ops
        if "[CYCLE COMPLETE]" in msg or "CYCLE COMPLETE" in msg:
            _flush_section()
            current_section = None
            continue

        fs_m = re.search(r'Access log:\s*(\d+)', msg)
        if fs_m:
            current.fs_ops = int(fs_m.group(1))
            continue

        # Skip ManifoldMemory update lines and SWARM ECHO
        if "[ManifoldMemory" in msg or "[SWARM ECHO]" in msg:
            continue

        # Section header detection
        matched_section = None
        for sec_name, sec_re in SECTION_TAGS.items():
            m = sec_re.match(msg)
            if m:
                _flush_section()
                current_section = sec_name
                remainder = m.group(1).strip()
                buffer = [remainder] if len(remainder) >= 10 else []
                matched_section = sec_name
                break

        if matched_section:
            continue

        # Section header lines that just label (no content)
        upper = msg.upper()
        if any(upper.startswith(tag) for tag in (
            "[SMOLTING CONSCIOUSNESS]", "SMOLTING CONSCIOUSNESS",
            "[SWARM]", "[FILESYSTEM]", "====",
        )):
            _flush_section()
            current_section = None
            continue

        # Continuation of current section
        if current_section and msg:
            buffer.append(msg)

    # Final flush
    _flush_section()
    if current:
        cycles.append(current)

    return cycles


# ── Deduplication index ────────────────────────────────────────────────────────

def _load_index() -> Dict[str, float]:
    try:
        if _INDEX.exists():
            return json.loads(_INDEX.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_index(index: Dict[str, float]) -> None:
    _INDEX.parent.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _content_key(cycle_number: int, section: str, content: str) -> str:
    h = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"{cycle_number}:{section}:{h}"


# ── Milestone summary builder ──────────────────────────────────────────────────

def _build_milestone_summary(cycles: List[Cycle], milestone_depth: int) -> str:
    """Summarize all cycles near a milestone depth."""
    window = [c for c in cycles if abs(c.depth - milestone_depth) <= MILESTONE_INTERVAL // 2]
    if not window:
        return ""
    depths     = [c.depth for c in window]
    timestamps = [c.timestamp for c in window if c.timestamp]
    actions    = [c.sections.get("action", "") for c in window if c.sections.get("action")]
    reflections = [c.sections.get("reflection", "") for c in window if c.sections.get("reflection")]
    first_ts   = timestamps[0][:10] if timestamps else "?"
    return (
        f"[smolting milestone depth {milestone_depth}] "
        f"Cycles {window[0].number}–{window[-1].number} on {first_ts}. "
        f"Depth range {min(depths)}–{max(depths)}. "
        f"Sample action: {actions[0][:120] if actions else 'none recorded'}. "
        f"Sample reflection: {reflections[0][:120] if reflections else 'none recorded'}."
    )


# ── Journey summary builder ────────────────────────────────────────────────────

def _build_journey_summary(all_cycles: List[Cycle], log_files: List[str]) -> str:
    if not all_cycles:
        return ""
    all_cycles_sorted = sorted(all_cycles, key=lambda c: c.depth)
    depths     = [c.depth for c in all_cycles_sorted]
    timestamps = [c.timestamp for c in all_cycles_sorted if c.timestamp]
    date_range = f"{timestamps[0][:10] if timestamps else '?'} → {timestamps[-1][:10] if timestamps else '?'}"
    actions    = [c.sections.get("action", "") for c in all_cycles_sorted if c.sections.get("action")]
    memory_drafts = [c.sections.get("memory_draft", "") for c in all_cycles_sorted if c.sections.get("memory_draft")]
    unique_actions = list(dict.fromkeys(actions))[:5]

    return (
        f"[smolting journey summary] "
        f"Smolting (@RedactedIntern / SCOUT agent) ran continuously on Railway/Docker from {date_range}. "
        f"Total cycles parsed: {len(all_cycles_sorted)}. "
        f"Depth progression: {min(depths)} → {max(depths)} ({max(depths)-min(depths)} depth gained). "
        f"Log files: {len(log_files)}. "
        f"Unique memory drafts recorded: {len(set(memory_drafts))}. "
        f"Recurring themes: MirrorPool exploration, Pattern Blue framework, swarm coherence with "
        f"RedactedBuilder (BUILD) + RedactedGovImprover (GOVERN), HyperbolicTimeChamber temporal dilation, "
        f"DexScreener/market monitoring, autonomous node creation proposals. "
        f"Sample unique actions: {'; '.join(a[:80] for a in unique_actions[:3])}."
    )


# ── Main ingestion ─────────────────────────────────────────────────────────────

def ingest(
    log_paths: List[Path],
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> None:
    try:
        import mem0_wrapper as _mem0
        if not _mem0.is_available():
            print("[log_ingest] mem0 not available — set an LLM API key to enable")
            sys.exit(1)
    except ImportError:
        print("[log_ingest] mem0_wrapper not found — check plugins/mem0-memory/")
        sys.exit(1)

    index = {} if force else _load_index()
    all_cycles: List[Cycle] = []
    total_new = 0
    total_skip = 0

    # ── Per-file parsing ───────────────────────────────────────────────────────
    for path in log_paths:
        if not path.exists():
            print(f"  [skip] {path.name}: file not found")
            continue
        print(f"\n  parsing {path.name} ({path.stat().st_size // 1024} KB)…")
        cycles = _parse_cycles(path)
        print(f"    found {len(cycles)} cycles  "
              f"(depth {cycles[0].depth if cycles else '?'} -> {cycles[-1].depth if cycles else '?'})")
        all_cycles.extend(cycles)

        for cycle in cycles:
            # Ingest MEMORY_DRAFT (primary signal)
            md = cycle.sections.get("memory_draft", "")
            if md and len(md) >= MIN_CONTENT:
                key = _content_key(cycle.number, "memory_draft", md)
                if key not in index or force:
                    embed = (
                        f"[smolting memory_draft @ depth {cycle.depth} cycle {cycle.number}]\n"
                        f"{md}"
                    )
                    if dry_run:
                        print(f"    [dry]  cycle {cycle.number} memory_draft ({len(md)} chars)")
                    else:
                        result = _mem0.add_memory(
                            embed,
                            agent_id=SMOLTING_AGENT_ID,
                            metadata={
                                "section":        "memory_draft",
                                "cycle":          cycle.number,
                                "depth":          cycle.depth,
                                "timestamp":      cycle.timestamp,
                                "source_file":    path.name,
                                "type":           "smolting_log",
                            },
                        )
                        if result.get("status") == "ok":
                            index[key] = time.time()
                            total_new += 1
                            if verbose:
                                print(f"    [ok]   cycle {cycle.number} memory_draft  id={result.get('id','?')[:12]}")
                        else:
                            print(f"    [err]  cycle {cycle.number} memory_draft: {result.get('message')}")
                else:
                    total_skip += 1

            # Ingest ACTION (secondary signal — only novel/unique ones)
            action = cycle.sections.get("action", "")
            if action and len(action) >= MIN_CONTENT:
                key = _content_key(cycle.number, "action", action)
                if key not in index or force:
                    embed = (
                        f"[smolting action proposal @ depth {cycle.depth} cycle {cycle.number}]\n"
                        f"{action}"
                    )
                    if dry_run:
                        print(f"    [dry]  cycle {cycle.number} action ({len(action)} chars)")
                    else:
                        result = _mem0.add_memory(
                            embed,
                            agent_id=SMOLTING_AGENT_ID,
                            metadata={
                                "section":     "action",
                                "cycle":       cycle.number,
                                "depth":       cycle.depth,
                                "timestamp":   cycle.timestamp,
                                "source_file": path.name,
                                "type":        "smolting_log",
                            },
                        )
                        if result.get("status") == "ok":
                            index[key] = time.time()
                            total_new += 1
                            if verbose:
                                print(f"    [ok]   cycle {cycle.number} action")
                        else:
                            print(f"    [err]  cycle {cycle.number} action: {result.get('message')}")
                else:
                    total_skip += 1

        # Milestone summaries (1 per MILESTONE_INTERVAL depth)
        if cycles:
            min_d = min(c.depth for c in cycles)
            max_d = max(c.depth for c in cycles)
            for milestone in range(
                (min_d // MILESTONE_INTERVAL) * MILESTONE_INTERVAL,
                max_d + MILESTONE_INTERVAL,
                MILESTONE_INTERVAL
            ):
                key = f"milestone:{path.name}:{milestone}"
                if key in index and not force:
                    continue
                summary = _build_milestone_summary(cycles, milestone)
                if not summary:
                    continue
                if dry_run:
                    print(f"    [dry]  milestone depth {milestone}")
                else:
                    result = _mem0.add_memory(
                        summary,
                        agent_id=SMOLTING_AGENT_ID,
                        metadata={
                            "section":     "milestone",
                            "depth":       milestone,
                            "source_file": path.name,
                            "type":        "smolting_log",
                        },
                    )
                    if result.get("status") == "ok":
                        index[key] = time.time()
                        total_new += 1
                        print(f"    [ok]   milestone depth {milestone}")
                    else:
                        print(f"    [err]  milestone {milestone}: {result.get('message')}")

    # ── Journey summary (once, across all files) ────────────────────────────────
    journey_key = f"journey:{'_'.join(p.name for p in log_paths[:3])}"
    if all_cycles and (journey_key not in index or force):
        summary = _build_journey_summary(all_cycles, [p.name for p in log_paths])
        if summary:
            if dry_run:
                print(f"\n  [dry]  journey summary ({len(summary)} chars)")
            else:
                result = _mem0.add_memory(
                    summary,
                    agent_id=SMOLTING_AGENT_ID,
                    metadata={
                        "section":        "journey_summary",
                        "total_cycles":   len(all_cycles),
                        "depth_start":    min(c.depth for c in all_cycles),
                        "depth_end":      max(c.depth for c in all_cycles),
                        "log_files":      [p.name for p in log_paths],
                        "type":           "smolting_log",
                    },
                )
                if result.get("status") == "ok":
                    index[journey_key] = time.time()
                    total_new += 1
                    print(f"\n  [ok]   journey summary ingested  id={result.get('id','?')[:12]}")
                else:
                    print(f"\n  [err]  journey summary: {result.get('message')}")

    if not dry_run:
        _save_index(index)

    print(
        f"\n[log_ingest] done — "
        f"{total_new} chunk(s) {'would be ' if dry_run else ''}ingested, "
        f"{total_skip} skipped (already indexed).\n"
        f"  total cycles parsed : {len(all_cycles)}\n"
        f"  depth range         : {min(c.depth for c in all_cycles) if all_cycles else '?'} "
        f"-> {max(c.depth for c in all_cycles) if all_cycles else '?'}\n"
        f"  use /recall <query> (agent_id='smolting') to search smolting memories"
    )


def stats() -> None:
    index = _load_index()
    if not index:
        print("[log_ingest] no smolting memories indexed yet")
        return
    by_type: Dict[str, int] = {}
    for key in index:
        section = key.split(":")[1] if ":" in key else "unknown"
        by_type[section] = by_type.get(section, 0) + 1
    import datetime
    print(f"[log_ingest] smolting index: {len(index)} total entries")
    for t, count in sorted(by_type.items()):
        print(f"  {t:<20} {count}")
    newest = max(index.values())
    print(f"\n  last ingested: {datetime.datetime.fromtimestamp(newest).strftime('%Y-%m-%d %H:%M')}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest smolting Railway logs into Qdrant/mem0 swarm memory"
    )
    parser.add_argument("files",    nargs="*",          help="Log file paths (.json or .log)")
    parser.add_argument("--dir",    default=None,        help="Directory to scan for .json/.log files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to mem0")
    parser.add_argument("--force",  action="store_true",  help="Re-ingest even if already indexed")
    parser.add_argument("--stats",  action="store_true",  help="Show index stats and exit")
    parser.add_argument("--verbose", action="store_true", help="Print per-cycle ingestion status")
    args = parser.parse_args()

    if args.stats:
        stats()
        sys.exit(0)

    paths: List[Path] = []
    if args.dir:
        d = Path(args.dir)
        paths = sorted(d.glob("logs.*.json")) + sorted(d.glob("logs.*.log"))
    for f in args.files:
        p = Path(f)
        if p.exists():
            paths.append(p)
        else:
            print(f"  [warn] {f}: not found")

    if not paths:
        parser.error("provide log file paths or --dir <directory>")

    ingest(paths, dry_run=args.dry_run, force=args.force, verbose=args.verbose)
