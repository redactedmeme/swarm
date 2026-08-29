#!/usr/bin/env python3
# python/docs_ingest.py
"""
Pattern Blue Docs — RAG Ingestion Pipeline
==========================================
Reads every .md file from docs/, splits them into section-level chunks,
and stores each chunk in the Qdrant/mem0 vector store under agent_id="docs".

Usage
-----
  python python/docs_ingest.py            # ingest all docs
  python python/docs_ingest.py --dry-run  # preview chunks without writing
  python python/docs_ingest.py --force    # re-ingest even if already indexed

After ingestion, use /docs <query> in the terminal to search across all Pattern
Blue documentation, or /recall from the "docs" agent namespace directly.

Storage
-------
  agent_id  : "docs"
  metadata  : { source_doc, section, doc_path, chunk_index, ingested_at }
  store     : fs/memories/ (Qdrant on-disk via mem0_wrapper)
"""

import sys
import os
import re
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Tuple

# ── Path setup ─────────────────────────────────────────────────────────────────
from swarm_core.paths import repo_root as _repo_root, mem0_dir as _mem0_dir
_ROOT    = _repo_root()
_DOCS    = _ROOT / "docs"
_MEM0    = _mem0_dir()
_INDEX   = _ROOT / "fs" / "docs_index.json"

if str(_MEM0) not in sys.path:
    sys.path.insert(0, str(_MEM0))

# ── Load .env if present ───────────────────────────────────────────────────────
_env_file = _ROOT / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

# ── Constants ──────────────────────────────────────────────────────────────────
DOCS_AGENT_ID     = "docs"
MIN_CHUNK_LENGTH  = 80       # chars — skip micro-fragments
MAX_CHUNK_LENGTH  = 1500     # chars — hard-truncate oversized chunks
SECTION_RE        = re.compile(r'^#{1,4}\s+(.+)$', re.MULTILINE)


# ── Chunker ────────────────────────────────────────────────────────────────────

def _split_by_heading(text: str, filename: str) -> List[Tuple[str, str]]:
    """
    Split a markdown document into (section_title, content) chunks.

    Strategy:
      - Split on any heading line (# through ####)
      - Include the heading itself as part of the chunk for context
      - Collapse runs of blank lines
      - Enforce min/max length
    """
    lines = text.splitlines()
    chunks: List[Tuple[str, str]] = []

    current_heading = filename  # fallback title = filename
    current_lines: List[str] = []

    def _flush():
        body = "\n".join(current_lines).strip()
        # Collapse 3+ blank lines into 2
        body = re.sub(r'\n{3,}', '\n\n', body)
        if len(body) >= MIN_CHUNK_LENGTH:
            # Hard-truncate (vector DB works best with bounded chunks)
            chunks.append((current_heading, body[:MAX_CHUNK_LENGTH]))

    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            _flush()
            current_heading = m.group(1).strip()
            current_lines = [line]   # include heading in chunk body for context
        else:
            current_lines.append(line)

    _flush()
    return chunks


# ── Index (deduplication) ──────────────────────────────────────────────────────

def _load_index() -> Dict[str, float]:
    """Load { chunk_key → ingested_at } index from disk."""
    try:
        if _INDEX.exists():
            return json.loads(_INDEX.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_index(index: Dict[str, float]) -> None:
    _INDEX.parent.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _chunk_key(doc_name: str, section: str, chunk_index: int) -> str:
    return f"{doc_name}::{section}::{chunk_index}"


# ── Ingest ─────────────────────────────────────────────────────────────────────

def ingest(dry_run: bool = False, force: bool = False) -> None:
    """Main ingestion entry point."""
    try:
        import mem0_wrapper as _mem0
        if not _mem0.is_available():
            print("[docs_ingest] mem0 not available — set an LLM API key to enable")
            print("  Supported: ANTHROPIC_API_KEY | OPENAI_API_KEY | XAI_API_KEY")
            sys.exit(1)
    except ImportError:
        print("[docs_ingest] mem0_wrapper not found — check plugins/mem0-memory/")
        sys.exit(1)

    index = {} if force else _load_index()

    md_files = sorted(_DOCS.glob("*.md"))
    if not md_files:
        print(f"[docs_ingest] no .md files found in {_DOCS}")
        return

    total_new = 0
    total_skip = 0

    for md_path in md_files:
        doc_name = md_path.stem
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  [skip] {doc_name}: read error — {e}")
            continue

        chunks = _split_by_heading(text, doc_name)
        print(f"\n  {doc_name}  ({len(chunks)} chunks)")

        for idx, (section, body) in enumerate(chunks):
            key = _chunk_key(doc_name, section, idx)

            if key in index and not force:
                total_skip += 1
                print(f"    [skip] [{idx}] {section[:55]}")
                continue

            # Build the text to embed — include doc name + section heading for
            # richer semantic context without relying on metadata filtering
            embed_text = (
                f"[{doc_name} / {section}]\n\n{body}"
            )

            if dry_run:
                print(f"    [dry]  [{idx}] {section[:55]}  ({len(embed_text)} chars)")
                total_new += 1
                continue

            result = _mem0.add_memory(
                embed_text,
                agent_id=DOCS_AGENT_ID,
                metadata={
                    "source_doc":   doc_name,
                    "section":      section,
                    "doc_path":     str(md_path.relative_to(_ROOT)),
                    "chunk_index":  idx,
                    "ingested_at":  time.time(),
                    "type":         "pattern_blue_doc",
                },
            )

            if result.get("status") == "ok":
                index[key] = time.time()
                total_new += 1
                print(f"    [ok]   [{idx}] {section[:55]}  id={result.get('id', '?')[:12]}")
            else:
                print(f"    [err]  [{idx}] {section[:55]}  — {result.get('message', 'unknown error')}")

    if not dry_run:
        _save_index(index)

    print(
        f"\n[docs_ingest] done — "
        f"{total_new} chunk(s) {'would be ' if dry_run else ''}ingested, "
        f"{total_skip} skipped (already indexed)."
    )
    if not dry_run and total_new > 0:
        print(
            f"  Use /docs <query> in the terminal to search, or:\n"
            f"  /recall <query>  (searches all memories including docs)"
        )


# ── Stats ──────────────────────────────────────────────────────────────────────

def stats() -> None:
    """Show ingestion index stats without touching mem0."""
    index = _load_index()
    if not index:
        print("[docs_ingest] no chunks indexed yet — run: python python/docs_ingest.py")
        return

    # Group by doc
    by_doc: Dict[str, int] = {}
    for key in index:
        doc = key.split("::")[0]
        by_doc[doc] = by_doc.get(doc, 0) + 1

    import datetime
    print(f"[docs_ingest] index: {len(index)} total chunk(s) across {len(by_doc)} doc(s)")
    for doc, count in sorted(by_doc.items()):
        print(f"  {doc:<45} {count} chunk(s)")

    newest_ts = max(index.values())
    print(f"\n  last ingested: {datetime.datetime.fromtimestamp(newest_ts).strftime('%Y-%m-%d %H:%M')}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Pattern Blue docs into Qdrant/mem0")
    parser.add_argument("--dry-run",  action="store_true", help="preview chunks without writing")
    parser.add_argument("--force",    action="store_true", help="re-ingest even if already indexed")
    parser.add_argument("--stats",    action="store_true", help="show index stats and exit")
    args = parser.parse_args()

    if args.stats:
        stats()
    else:
        ingest(dry_run=args.dry_run, force=args.force)
