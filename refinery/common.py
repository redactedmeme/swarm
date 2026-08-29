"""Shared substrate for swarm-refinery: config, Postgres, Qdrant, embeddings.

All ingesters and refiners route writes through `upsert_signal` so a row lands in
Postgres (`signals`) and Qdrant (`swarm_signals`) atomically-enough and idempotently
(same id => update, not duplicate).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger("refinery")

# ── Config ────────────────────────────────────────────────────────────────────
REDIS_URL    = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://swarm:swarm_secret@127.0.0.1:5432/swarm")
QDRANT_URL   = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "swarm_signals")

EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_DIM   = int(os.getenv("EMBED_DIM", "384"))

# Source volume mounts (read-only) inside the container.
SRC_SMOLTING     = os.getenv("SRC_SMOLTING", "/sources/smolting")
SRC_HERMES       = os.getenv("SRC_HERMES", "/sources/hermes")
SRC_REDACTED_CHAN = os.getenv("SRC_REDACTED_CHAN", "/sources/redacted-chan")

# $REDACTED token mint
TOKEN_MINT = os.getenv("TOKEN_MINT", "9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump")

# Safety: pruning consumed Redis keys is OFF by default.
PRUNE = os.getenv("REFINERY_PRUNE", "false").lower() in ("1", "true", "yes")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sig_id(source: str, natural_key: str) -> str:
    """Deterministic id so re-ingesting the same source row updates in place."""
    h = hashlib.sha1(f"{source}:{natural_key}".encode("utf-8")).hexdigest()[:24]
    return f"{source}_{h}"


# ── Postgres (thread-local: scheduler thread + API handlers must not share one
#    psycopg2 connection) ───────────────────────────────────────────────────
import threading as _threading
_pg_local = _threading.local()


def pg():
    conn = getattr(_pg_local, "conn", None)
    if conn is None or conn.closed:
        import psycopg2
        from pgvector.psycopg2 import register_vector
        conn = psycopg2.connect(POSTGRES_URL)
        conn.autocommit = True
        register_vector(conn)
        _pg_local.conn = conn
        logger.info("[pg] connected (thread=%s)", _threading.current_thread().name)
    return conn


def signals_count() -> int:
    with pg().cursor() as cur:
        cur.execute("SELECT count(*) FROM signals")
        return cur.fetchone()[0]


def init_schema(schema_path: str) -> None:
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()
    with pg().cursor() as cur:
        cur.execute(sql)
    logger.info("[pg] schema applied")


def get_cursor(ingester: str) -> str:
    with pg().cursor() as cur:
        cur.execute("SELECT cursor FROM ingest_cursors WHERE ingester=%s", (ingester,))
        row = cur.fetchone()
        return row[0] if row else ""


def set_cursor(ingester: str, cursor: str, stats: dict | None = None) -> None:
    with pg().cursor() as cur:
        cur.execute(
            """INSERT INTO ingest_cursors (ingester, cursor, updated_at, stats)
               VALUES (%s, %s, now(), %s)
               ON CONFLICT (ingester) DO UPDATE
                 SET cursor=EXCLUDED.cursor, updated_at=now(), stats=EXCLUDED.stats""",
            (ingester, cursor, json.dumps(stats or {})),
        )


# ── Qdrant ──────────────────────────────────────────────────────────────────
_qdrant = None


def qdrant():
    global _qdrant
    if _qdrant is None:
        from qdrant_client import QdrantClient
        _qdrant = QdrantClient(url=QDRANT_URL, timeout=30)
    return _qdrant


def ensure_qdrant_collection() -> None:
    from qdrant_client.models import Distance, VectorParams
    client = qdrant()
    existing = {c.name for c in client.get_collections().collections}
    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        logger.info("[qdrant] created collection %s (dim=%d)", QDRANT_COLLECTION, EMBED_DIM)


def _qdrant_point_id(sig_id_str: str) -> str:
    # Qdrant needs uint or UUID ids; derive a stable UUID from the signal id.
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, sig_id_str))


# ── Embeddings (sentence-transformers, on-box, free) ─────────────────────────
_model = None


def _embedder():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("[embed] loading %s", EMBED_MODEL)
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def embed(text: str) -> list[float]:
    vec = _embedder().encode(text or " ", normalize_embeddings=True)
    return vec.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vecs = _embedder().encode(texts, normalize_embeddings=True, batch_size=64)
    return [v.tolist() for v in vecs]


# ── Unified write ─────────────────────────────────────────────────────────────
def upsert_signal(
    *,
    id: str,
    source: str,
    kind: str,
    text: str,
    ts: str | None = None,
    provenance: dict | None = None,
    confidence: float = 1.0,
    private: bool = False,
    embedding: list[float] | None = None,
) -> None:
    """Upsert one signal into Postgres + Qdrant. Private rows still go to Qdrant
    (on-box volume) but are flagged so the API can withhold them from external
    consumers."""
    text = (text or "").strip()
    if not text:
        return
    if embedding is None:
        embedding = embed(text)
    prov = provenance or {}
    ts = ts or now_iso()

    with pg().cursor() as cur:
        cur.execute(
            """INSERT INTO signals (id, source, kind, text, ts, provenance, confidence, private, embedding)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                 text=EXCLUDED.text, kind=EXCLUDED.kind, ts=EXCLUDED.ts,
                 provenance=EXCLUDED.provenance, confidence=EXCLUDED.confidence,
                 private=EXCLUDED.private, embedding=EXCLUDED.embedding""",
            (id, source, kind, text[:8000], ts, json.dumps(prov), confidence, private, embedding),
        )

    try:
        from qdrant_client.models import PointStruct
        qdrant().upsert(
            collection_name=QDRANT_COLLECTION,
            points=[PointStruct(
                id=_qdrant_point_id(id),
                vector=embedding,
                payload={
                    "signal_id": id, "source": source, "kind": kind,
                    "ts": ts, "private": private,
                    "text": text[:512],
                },
            )],
        )
    except Exception as e:
        logger.warning("[qdrant] upsert failed for %s: %s", id, e)


# ── Optional LLM enrichment — OpenRouter (deepseek) primary, Groq fallback ────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
_llm = None
_llm_kind = None  # "openrouter" | "groq"


def _get_llm():
    """Lazily build an OpenAI-compatible client. Prefer the local redacted-proxy
    (centralized routing + privacy), then OpenRouter direct, then Groq direct."""
    global _llm, _llm_kind
    if _llm is not None:
        return _llm, _llm_kind
    from openai import OpenAI
    proxy_url = os.getenv("PROXY_URL", "").rstrip("/")
    proxy_token = os.getenv("PROXY_TOKEN", "")
    if proxy_url and proxy_token:
        _llm = OpenAI(api_key=proxy_token, base_url=f"{proxy_url}/v1")
        _llm_kind = "proxy"
    elif OPENROUTER_API_KEY:
        _llm = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
        _llm_kind = "openrouter"
    elif GROQ_API_KEY:
        _llm = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
        _llm_kind = "groq"
    return _llm, _llm_kind


# ── LLM output sanitization (strip leaked chain-of-thought) ──────────────────
# deepseek-v4-flash is a reasoning model; when reasoning isn't disabled it dumps
# its chain-of-thought into `content` ("Here's a thinking process: 1. Analyze
# User Input..."). We disable reasoning at the source AND scrub defensively so a
# signal is never stored as raw meta-reasoning that poisons downstream consumers
# (e.g. redactedbuilder grounds its group posts on these signals).
_THINK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)
_LEAK_SIGNALS = (
    "here's a thinking process", "here is a thinking process",
    "analyze user input", "deconstruct the input", "let me analyze",
    "let me think", "the user wants", "the user is asking",
    "1.  **", "1. **analyze", "**analyze user",
)


def _strip_reasoning(text: str) -> str:
    """Drop leaked <think>/<reasoning> blocks. Never raises."""
    if not text:
        return text
    try:
        return _THINK_RE.sub("", text).strip()
    except Exception:
        return text


def _looks_like_reasoning(text: str) -> bool:
    """True if the candidate reads as leaked chain-of-thought rather than a real
    one-line summary. Fail-closed gate: a false positive drops one signal, a
    false negative stores CoT sludge that poisons every downstream consumer."""
    if not text:
        return False
    low = text.lower()
    return any(sig in low for sig in _LEAK_SIGNALS)


def summarize(prompt: str, system: str = "You are a terse analyst. Reply in one sentence.") -> str | None:
    """Best-effort LLM summary. OpenRouter/deepseek primary (reasoning disabled so
    terse outputs aren't eaten by chain-of-thought), Groq fallback. Returns None
    if unavailable — callers must degrade gracefully."""
    client, kind = _get_llm()
    if client is None:
        return None
    try:
        model = GROQ_MODEL if kind == "groq" else OPENROUTER_MODEL
        kwargs = dict(model=model, temperature=0.3, max_tokens=300,
                      messages=[{"role": "system", "content": system},
                                {"role": "user", "content": prompt[:6000]}])
        if kind in ("openrouter", "proxy"):
            # deepseek-v4-flash is a reasoning model; disable reasoning so `content`
            # holds the answer instead of chain-of-thought. Send it for the proxy
            # path too — the proxy forwards extra_body and strips it for providers
            # that reject it, so relying on central injection was leaking CoT here.
            kwargs["extra_body"] = {"reasoning": {"enabled": False}}
        resp = client.chat.completions.create(**kwargs)
        out = _strip_reasoning((resp.choices[0].message.content or "").strip())
        # Fail closed: never store a signal that's still leaked meta-reasoning.
        if not out or _looks_like_reasoning(out):
            logger.warning("[llm] summarize dropped leaked-reasoning output (%s): %s",
                           _llm_kind, (out or "")[:80])
            return None
        return out
    except Exception as e:
        logger.warning("[llm] summarize failed (%s): %s", _llm_kind, e)
        return None


def upsert_batch(rows: list[dict], batch_size: int = 256) -> int:
    """Batch-embed and upsert many signal rows. Each row is a dict with the same
    keys as upsert_signal (embedding is computed here). Returns count written."""
    written = 0
    for i in range(0, len(rows), batch_size):
        chunk = [r for r in rows[i:i + batch_size] if (r.get("text") or "").strip()]
        if not chunk:
            continue
        vecs = embed_batch([r["text"] for r in chunk])
        for r, v in zip(chunk, vecs):
            upsert_signal(
                id=r["id"], source=r["source"], kind=r["kind"], text=r["text"],
                ts=r.get("ts"), provenance=r.get("provenance"),
                confidence=r.get("confidence", 1.0), private=r.get("private", False),
                embedding=v,
            )
            written += 1
    return written
