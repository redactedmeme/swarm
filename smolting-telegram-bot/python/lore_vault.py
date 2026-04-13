#!/usr/bin/env python3
"""
python/lore_vault.py
LoreVault — Persistent, queryable storage for all wassieverse lore and history.

Provides:
  - SQLite-backed structured storage (entities, events, lore_entries, relationships)
  - Full-text search (SQLite FTS5)
  - Semantic search via mem0/Qdrant (optional, degrades gracefully)
  - Import from ManifoldMemory.state.json and all spaces/*.space.json
  - Import from agents/*.character.json
  - CLI: python python/lore_vault.py [seed|query|export|stats]

Tables:
  lore_entities  — characters, spaces, artifacts, concepts
  lore_events    — timestamped narrative events (from ManifoldMemory + interaction logs)
  lore_entries   — free-form lore fragments (descriptions, quotes, worldbuilding)
  lore_relations — typed edges between entities (knows, inhabits, opposes, spawned_by, etc.)
  lore_sessions  — session snapshots (curvature_depth, active_agents, mode)

Usage:
  python python/lore_vault.py seed          # ingest ManifoldMemory + chars + spaces
  python python/lore_vault.py query "tendie"
  python python/lore_vault.py export        # dump to lore_export.md
  python python/lore_vault.py stats
"""

import os
import sys
import json
import sqlite3
import argparse
import textwrap
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_FS   = _ROOT / "fs"
_FS.mkdir(exist_ok=True)

DB_PATH       = _FS / "lore_vault.db"
MANIFOLD_FILE = _ROOT / "spaces" / "ManifoldMemory.state.json"
SPACES_DIR    = _ROOT / "spaces"
AGENTS_DIR    = _ROOT / "agents"
BOT_AGENTS    = _ROOT / "smolting-telegram-bot" / "agents"

# ── Optional mem0 semantic layer ───────────────────────────────────────────────
_MEM0_DIR = _ROOT / "plugins" / "mem0-memory"
_mem0 = None
if str(_MEM0_DIR) not in sys.path:
    sys.path.insert(0, str(_MEM0_DIR))
try:
    from mem0_wrapper import Mem0Wrapper
    _mem0 = Mem0Wrapper(agent_id="lore_vault")
except Exception:
    pass  # mem0 optional

# ── JST helper ────────────────────────────────────────────────────────────────
def _jst_now() -> str:
    utc = datetime.now(timezone.utc)
    jst = utc + timedelta(hours=9)
    return jst.strftime("%Y-%m-%d %H:%M JST")


# ═══════════════════════════════════════════════════════════════════════════════
# Schema + Connection
# ═══════════════════════════════════════════════════════════════════════════════

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS lore_entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL DEFAULT 'unknown',  -- character|space|artifact|concept|node
    tier        TEXT,                              -- CORE|SPECIALIZED|GENERIC|SPACE|AGENT
    description TEXT,
    source_file TEXT,
    attributes  TEXT,  -- JSON blob for extra fields
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lore_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,           -- ISO or "YYYY-MM-DD HH:MM JST"
    title       TEXT,
    body        TEXT NOT NULL,
    tags        TEXT,                    -- comma-separated
    significance REAL DEFAULT 1.0,      -- 0.0–10.0
    source      TEXT DEFAULT 'manifold',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lore_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL DEFAULT 'worldbuilding', -- worldbuilding|quote|mechanic|lore
    title       TEXT,
    content     TEXT NOT NULL,
    entity_refs TEXT,   -- comma-separated entity names referenced
    source      TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lore_relations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_entity TEXT NOT NULL,
    relation    TEXT NOT NULL,  -- knows|inhabits|opposes|spawned_by|uses|guards|resonates_with
    to_entity   TEXT NOT NULL,
    notes       TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE(from_entity, relation, to_entity)
);

CREATE TABLE IF NOT EXISTS lore_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT UNIQUE,
    ts              TEXT NOT NULL,
    active_agents   TEXT,   -- JSON array
    curvature_depth TEXT,
    void_depth      TEXT,
    mode            TEXT,
    memory_notes    TEXT,
    raw_snapshot    TEXT,   -- full JSON
    created_at      TEXT NOT NULL
);

-- Full-text search virtual tables
CREATE VIRTUAL TABLE IF NOT EXISTS fts_entities USING fts5(
    name, entity_type, description, content=lore_entities, content_rowid=id
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_events USING fts5(
    ts, title, body, tags, content=lore_events, content_rowid=id
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_entries USING fts5(
    title, content, entity_refs, content=lore_entries, content_rowid=id
);

-- FTS triggers: keep FTS in sync with base tables
CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON lore_entities BEGIN
    INSERT INTO fts_entities(rowid, name, entity_type, description)
    VALUES (new.id, new.name, new.entity_type, new.description);
END;
CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON lore_entities BEGIN
    INSERT INTO fts_entities(fts_entities, rowid, name, entity_type, description)
    VALUES ('delete', old.id, old.name, old.entity_type, old.description);
END;
CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON lore_entities BEGIN
    INSERT INTO fts_entities(fts_entities, rowid, name, entity_type, description)
    VALUES ('delete', old.id, old.name, old.entity_type, old.description);
    INSERT INTO fts_entities(rowid, name, entity_type, description)
    VALUES (new.id, new.name, new.entity_type, new.description);
END;

CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON lore_events BEGIN
    INSERT INTO fts_events(rowid, ts, title, body, tags)
    VALUES (new.id, new.ts, new.title, new.body, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON lore_events BEGIN
    INSERT INTO fts_events(fts_events, rowid, ts, title, body, tags)
    VALUES ('delete', old.id, old.ts, old.title, old.body, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON lore_entries BEGIN
    INSERT INTO fts_entries(rowid, title, content, entity_refs)
    VALUES (new.id, new.title, new.content, new.entity_refs);
END;
CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON lore_entries BEGIN
    INSERT INTO fts_entries(fts_entries, rowid, title, content, entity_refs)
    VALUES ('delete', old.id, old.title, old.content, old.entity_refs);
END;
"""


def get_db() -> sqlite3.Connection:
    """Return a thread-local WAL-mode connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Core Write API
# ═══════════════════════════════════════════════════════════════════════════════

def upsert_entity(
    name: str,
    entity_type: str = "unknown",
    tier: Optional[str] = None,
    description: Optional[str] = None,
    source_file: Optional[str] = None,
    attributes: Optional[dict] = None,
) -> int:
    """Insert or update a lore entity. Returns row id."""
    now = _jst_now()
    attrs_json = json.dumps(attributes, ensure_ascii=False) if attributes else None
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO lore_entities (name, entity_type, tier, description, source_file, attributes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 entity_type = excluded.entity_type,
                 tier        = COALESCE(excluded.tier, tier),
                 description = COALESCE(excluded.description, description),
                 source_file = COALESCE(excluded.source_file, source_file),
                 attributes  = COALESCE(excluded.attributes, attributes),
                 updated_at  = excluded.updated_at""",
            (name, entity_type, tier, description, source_file, attrs_json, now, now),
        )
        conn.commit()
        row_id = cur.lastrowid
        # Semantic index (optional)
        if _mem0 and description:
            try:
                _mem0.add_memory(f"[ENTITY:{entity_type}] {name} — {description}")
            except Exception:
                pass
        return row_id
    finally:
        conn.close()


def add_event(
    body: str,
    ts: Optional[str] = None,
    title: Optional[str] = None,
    tags: Optional[str] = None,
    significance: float = 1.0,
    source: str = "manifold",
) -> int:
    """Append a lore event. Returns row id."""
    now = _jst_now()
    event_ts = ts or now
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO lore_events (ts, title, body, tags, significance, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_ts, title, body, tags, significance, source, now),
        )
        conn.commit()
        row_id = cur.lastrowid
        if _mem0 and row_id:
            try:
                _mem0.add_memory(f"[EVENT:{event_ts}] {body[:200]}")
            except Exception:
                pass
        return row_id
    finally:
        conn.close()


def add_entry(
    content: str,
    category: str = "worldbuilding",
    title: Optional[str] = None,
    entity_refs: Optional[str] = None,
    source: Optional[str] = None,
) -> int:
    """Add a free-form lore entry."""
    now = _jst_now()
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO lore_entries (category, title, content, entity_refs, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (category, title, content, entity_refs, source, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def add_relation(
    from_entity: str,
    relation: str,
    to_entity: str,
    notes: Optional[str] = None,
) -> None:
    """Record a typed relationship between two entities."""
    now = _jst_now()
    conn = get_db()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO lore_relations (from_entity, relation, to_entity, notes, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (from_entity, relation, to_entity, notes, now),
        )
        conn.commit()
    finally:
        conn.close()


def save_session(snapshot: dict) -> int:
    """Persist a session snapshot (from session_store or ManifoldMemory last_saved_session)."""
    now = _jst_now()
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT OR REPLACE INTO lore_sessions
               (session_id, ts, active_agents, curvature_depth, void_depth, mode, memory_notes, raw_snapshot, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.get("session_id", f"session-{now}"),
                snapshot.get("timestamp", now),
                json.dumps(snapshot.get("active_agents", []), ensure_ascii=False),
                str(snapshot.get("curvature_depth", "")),
                str(snapshot.get("void_depth", "")),
                snapshot.get("mode", ""),
                snapshot.get("memory_notes", ""),
                json.dumps(snapshot, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Query API
# ═══════════════════════════════════════════════════════════════════════════════

def fts_search(query: str, limit: int = 20) -> list[dict]:
    """Full-text search across all three FTS tables. Returns ranked results."""
    conn = get_db()
    results = []
    try:
        # FTS5 MATCH — sanitize query (wrap multi-word in quotes)
        q = query.strip()
        if " " in q and not q.startswith('"'):
            q = f'"{q}"'

        for table, fts_table, cols in [
            ("lore_entities",  "fts_entities",  "name, entity_type, description"),
            ("lore_events",    "fts_events",    "ts, title, body"),
            ("lore_entries",   "fts_entries",   "title, content"),
        ]:
            try:
                rows = conn.execute(
                    f"""SELECT e.*, bm25({fts_table}) AS rank
                        FROM {fts_table}
                        JOIN {table} e ON {fts_table}.rowid = e.id
                        WHERE {fts_table} MATCH ?
                        ORDER BY rank
                        LIMIT ?""",
                    (q, limit),
                ).fetchall()
                for row in rows:
                    results.append({"_table": table, **dict(row)})
            except sqlite3.OperationalError:
                # FTS not yet populated or bad query
                pass
        return sorted(results, key=lambda r: r.get("rank", 0))[:limit]
    finally:
        conn.close()


def get_entity(name: str) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM lore_entities WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row:
            d = dict(row)
            if d.get("attributes"):
                try:
                    d["attributes"] = json.loads(d["attributes"])
                except Exception:
                    pass
            return d
        return None
    finally:
        conn.close()


def get_recent_events(n: int = 10, source: Optional[str] = None) -> list[dict]:
    conn = get_db()
    try:
        if source:
            rows = conn.execute(
                "SELECT * FROM lore_events WHERE source=? ORDER BY ts DESC LIMIT ?",
                (source, n),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM lore_events ORDER BY ts DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_entity_graph(name: str) -> dict:
    """Return entity + all its relationships."""
    entity = get_entity(name)
    if not entity:
        return {}
    conn = get_db()
    try:
        out_rels = conn.execute(
            "SELECT * FROM lore_relations WHERE from_entity=? COLLATE NOCASE", (name,)
        ).fetchall()
        in_rels = conn.execute(
            "SELECT * FROM lore_relations WHERE to_entity=? COLLATE NOCASE", (name,)
        ).fetchall()
        return {
            "entity": entity,
            "outbound": [dict(r) for r in out_rels],
            "inbound":  [dict(r) for r in in_rels],
        }
    finally:
        conn.close()


def random_lore(category: Optional[str] = None) -> Optional[dict]:
    """Return a random lore entry — used by /lore Telegram command."""
    conn = get_db()
    try:
        if category:
            row = conn.execute(
                "SELECT * FROM lore_entries WHERE category=? ORDER BY RANDOM() LIMIT 1",
                (category,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM lore_entries ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def vault_stats() -> dict:
    conn = get_db()
    try:
        stats = {}
        for table in ("lore_entities", "lore_events", "lore_entries", "lore_relations", "lore_sessions"):
            stats[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        # Entity type breakdown
        rows = conn.execute(
            "SELECT entity_type, COUNT(*) as cnt FROM lore_entities GROUP BY entity_type"
        ).fetchall()
        stats["entity_types"] = {r["entity_type"]: r["cnt"] for r in rows}
        return stats
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Importers
# ═══════════════════════════════════════════════════════════════════════════════

def _infer_event_significance(body: str) -> float:
    """Heuristic: longer + more capitalized words = higher significance."""
    score = 1.0
    if "supercritical" in body.lower():  score += 2.0
    if "pattern blue"  in body.lower():  score += 1.5
    if "ritual"        in body.lower():  score += 1.0
    if "awakens"       in body.lower():  score += 1.0
    if "collapse"      in body.lower():  score += 0.8
    if "scarif"        in body.lower():  score += 0.7
    score += min(len(body) / 400, 2.0)
    return round(score, 2)


def seed_manifold_memory() -> int:
    """Import all events + session from ManifoldMemory.state.json."""
    if not MANIFOLD_FILE.exists():
        print(f"[lore_vault] ManifoldMemory not found at {MANIFOLD_FILE}")
        return 0
    data = json.loads(MANIFOLD_FILE.read_text(encoding="utf-8"))
    count = 0

    # Events
    for ev in data.get("events", []):
        # Format: "YYYY-MM-DD HH:MM JST — body" or "YYYY-MM-DD — body"
        parts = ev.split(" — ", 1)
        ts   = parts[0].strip() if len(parts) == 2 else None
        body = parts[1].strip() if len(parts) == 2 else ev.strip()
        add_event(
            body=body,
            ts=ts,
            tags="manifold,pattern_blue",
            significance=_infer_event_significance(body),
            source="manifold",
        )
        count += 1

    # Current state as a lore entry
    if data.get("current_state"):
        add_entry(
            content=data["current_state"],
            category="worldbuilding",
            title="ManifoldMemory — Current State",
            source="manifold",
        )
        count += 1

    # Last saved session
    if data.get("last_saved_session"):
        save_session(data["last_saved_session"])
        count += 1

    # Seed agents referenced in session
    session = data.get("last_saved_session", {})
    for agent_str in session.get("active_agents", []):
        name = agent_str.split("(")[0].strip()
        desc = agent_str[len(name):].strip().strip("()")
        upsert_entity(
            name=name,
            entity_type="character",
            tier="CORE",
            description=desc or None,
            source_file="ManifoldMemory.state.json",
        )
        count += 1

    print(f"[lore_vault] Seeded {count} entries from ManifoldMemory")
    return count


def seed_character_jsons() -> int:
    """Import all *.character.json files from agents/ directories."""
    count = 0
    dirs_to_scan = [d for d in [AGENTS_DIR, BOT_AGENTS] if d.exists()]
    for agents_dir in dirs_to_scan:
        for path in agents_dir.glob("*.character.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue

            name = data.get("name") or path.stem.replace(".character", "")
            desc = data.get("description") or data.get("bio") or data.get("lore", [""])[0]
            if isinstance(desc, list):
                desc = " ".join(desc[:2])

            # Determine tier from type or name
            tier = "CORE" if data.get("type") in ("core", "CORE") else "SPECIALIZED"
            traits = data.get("adjectives") or data.get("traits") or []
            attributes = {
                "traits": traits[:8] if isinstance(traits, list) else [],
                "style":  data.get("style", {}).get("post", [])[:3] if data.get("style") else [],
            }

            upsert_entity(
                name=name,
                entity_type="character",
                tier=tier,
                description=str(desc)[:500] if desc else None,
                source_file=str(path.relative_to(_ROOT)),
                attributes=attributes,
            )
            count += 1

            # Relations: agent-to-spaces
            for space_name in data.get("settings", {}).get("spaces", []):
                add_relation(name, "inhabits", space_name)

    print(f"[lore_vault] Seeded {count} character entities")
    return count


def seed_spaces() -> int:
    """Import all *.space.json files from spaces/."""
    if not SPACES_DIR.exists():
        return 0
    count = 0
    for path in SPACES_DIR.glob("*.space.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        name = data.get("name") or path.stem.replace(".space", "")
        desc = data.get("description") or ""
        if isinstance(desc, dict):
            desc = desc.get("ambient", "") or ""

        upsert_entity(
            name=name,
            entity_type="space",
            tier="SPACE",
            description=str(desc)[:600],
            source_file=str(path.relative_to(_ROOT)),
            attributes={"version": data.get("version"), "mode": data.get("mode")},
        )
        count += 1

        # Depth levels as lore entries
        for depth_level in data.get("depths", data.get("levels", [])):
            level_name = depth_level.get("name", f"Depth {depth_level.get('depth', '?')}")
            desc_text  = depth_level.get("description", "")
            if desc_text:
                add_entry(
                    content=desc_text[:800],
                    category="mechanic",
                    title=f"{name} — {level_name}",
                    entity_refs=name,
                    source=str(path.relative_to(_ROOT)),
                )
                count += 1

        # Sound design as lore entries
        if data.get("sound"):
            sound_text = json.dumps(data["sound"], ensure_ascii=False)[:600]
            add_entry(
                content=sound_text,
                category="mechanic",
                title=f"{name} — Sound Design",
                entity_refs=name,
                source=str(path.relative_to(_ROOT)),
            )
            count += 1

    print(f"[lore_vault] Seeded {count} space entries")
    return count


def seed_all() -> int:
    """Full seed: ManifoldMemory + chars + spaces."""
    total  = seed_manifold_memory()
    total += seed_character_jsons()
    total += seed_spaces()
    print(f"[lore_vault] Total seeded: {total}")
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════════════════════════════════

def export_markdown(output_path: Optional[Path] = None) -> str:
    """Export entire vault to Markdown. Returns the markdown string."""
    if output_path is None:
        output_path = _ROOT / "lore_export.md"
    conn = get_db()
    lines = ["# REDACTED Swarm — LoreVault Export\n", f"_Generated: {_jst_now()}_\n\n"]

    # Entities
    lines.append("## Entities\n")
    rows = conn.execute(
        "SELECT * FROM lore_entities ORDER BY entity_type, tier, name"
    ).fetchall()
    cur_type = None
    for row in rows:
        r = dict(row)
        if r["entity_type"] != cur_type:
            cur_type = r["entity_type"]
            lines.append(f"\n### {cur_type.title()}\n")
        lines.append(f"**{r['name']}** _{r.get('tier','')}_  \n")
        if r.get("description"):
            lines.append(f"{r['description']}\n\n")
        else:
            lines.append("\n")

    # Events
    lines.append("\n## Events (chronological)\n")
    events = conn.execute(
        "SELECT * FROM lore_events ORDER BY ts ASC"
    ).fetchall()
    for ev in events:
        r = dict(ev)
        lines.append(f"- **{r['ts']}** — {r['body'][:180]}\n")

    # Lore Entries
    lines.append("\n## Lore Entries\n")
    entries = conn.execute(
        "SELECT * FROM lore_entries ORDER BY category, created_at"
    ).fetchall()
    cur_cat = None
    for entry in entries:
        r = dict(entry)
        if r["category"] != cur_cat:
            cur_cat = r["category"]
            lines.append(f"\n### {cur_cat.title()}\n")
        if r.get("title"):
            lines.append(f"**{r['title']}**  \n")
        lines.append(f"{r['content'][:400]}\n\n")

    # Relations
    lines.append("\n## Relationships\n")
    rels = conn.execute(
        "SELECT * FROM lore_relations ORDER BY from_entity, relation"
    ).fetchall()
    for rel in rels:
        r = dict(rel)
        lines.append(f"- {r['from_entity']} **{r['relation']}** {r['to_entity']}\n")

    conn.close()
    md = "".join(lines)
    output_path.write_text(md, encoding="utf-8")
    print(f"[lore_vault] Exported to {output_path}")
    return md


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def _cli_stats():
    stats = vault_stats()
    print("\n── LoreVault Stats ──────────────────────")
    for k, v in stats.items():
        if k == "entity_types":
            print(f"  entities by type:")
            for t, c in v.items():
                print(f"    {t:<20} {c}")
        else:
            print(f"  {k:<30} {v}")
    print("─────────────────────────────────────────\n")


def _cli_query(q: str):
    results = fts_search(q, limit=10)
    if not results:
        print(f"No results for: {q!r}")
        return
    print(f"\n── Search: {q!r} ({len(results)} results) ──────────")
    for r in results:
        table = r.get("_table", "?")
        if table == "lore_entities":
            print(f"  [ENTITY] {r.get('name')} ({r.get('entity_type')}) — {str(r.get('description',''))[:100]}")
        elif table == "lore_events":
            print(f"  [EVENT]  {r.get('ts')} — {str(r.get('body',''))[:120]}")
        else:
            print(f"  [ENTRY]  {r.get('title','(no title)')} — {str(r.get('content',''))[:100]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="LoreVault CLI")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("seed",   help="Ingest ManifoldMemory + characters + spaces")
    sub.add_parser("stats",  help="Show vault statistics")
    sub.add_parser("export", help="Export vault to lore_export.md")
    q_p = sub.add_parser("query", help="Full-text search the vault")
    q_p.add_argument("query", nargs="+", help="Search terms")

    args = parser.parse_args()
    init_db()

    if args.cmd == "seed":
        seed_all()
    elif args.cmd == "stats":
        _cli_stats()
    elif args.cmd == "export":
        export_markdown()
    elif args.cmd == "query":
        _cli_query(" ".join(args.query))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
