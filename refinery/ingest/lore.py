"""Ingest lore from smolting `lore_vault.db` (FTS5) if present.

The vault is optional — not currently provisioned on the box — so this ingester
discovers candidate DBs across mounted volumes and skips gracefully when none
exist. Reads whatever text-bearing table it can find (FTS5 `lore` / `documents`).
"""
from __future__ import annotations

import logging
import os
import sqlite3

import common as C

logger = logging.getLogger("refinery.lore")
INGESTER = "lore"

_CANDIDATES = [
    (os.path.join(C.SRC_SMOLTING, "fs", "lore_vault.db"), "lore", False),
    (os.path.join(C.SRC_SMOLTING, "lore_vault.db"), "lore", False),
    (os.path.join(C.SRC_REDACTED_CHAN, "lore_vault.db"), "lore", True),
]

# Column names we treat as the lore body, in priority order.
_TEXT_COLS = ("content", "text", "body", "chunk", "entry", "lore")


def _ingest_db(db_path: str, source: str, private: bool) -> int:
    if not os.path.exists(db_path):
        return 0
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    rows: list[dict] = []
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")]
        for tbl in tables:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info('{tbl}')")]
            text_col = next((c for c in _TEXT_COLS if c in cols), None)
            if not text_col:
                continue
            id_col = "rowid" if "id" not in cols else "id"
            for r in conn.execute(f"SELECT {id_col} AS rid, {text_col} AS body FROM '{tbl}'"):
                body = (r["body"] or "").strip()
                if not body:
                    continue
                rows.append({
                    "id": C.sig_id(source, f"{tbl}:{r['rid']}"),
                    "source": source, "kind": "raw_lore", "text": body,
                    "private": private,
                    "provenance": {"db": os.path.basename(db_path), "table": tbl},
                })
    finally:
        conn.close()
    return C.upsert_batch(rows)


def run() -> dict:
    total = 0
    seen = []
    for db_path, source, private in _CANDIDATES:
        n = _ingest_db(db_path, source, private)
        if n:
            seen.append({"db": db_path, "written": n})
        total += n
    stats = {"written": total, "dbs": seen}
    C.set_cursor(INGESTER, C.now_iso(), stats)
    logger.info("[lore] %s", stats)
    return stats
