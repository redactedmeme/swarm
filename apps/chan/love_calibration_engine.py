# redacted-chan-bot/love_calibration_engine.py
"""
Love Calibration Engine — relational memory retrieval for redacted-chan.

Retrieves vault memories using four axes:
  1. Emotional Alignment  (0.35) — memory's tone matches current moment
  2. Phi Depth Gate       (0.20) — deeper phi unlocks deeper memories
  3. Semantic Relevance   (0.25) — topical overlap via ChromaDB (FTS5 fallback)
  4. Learned Resonance    (0.20) — did surfacing this memory deepen connection before?

Calibration loop: after injecting a memory, detect outcome on the NEXT message.
Update memory's love_resonance score based on whether it landed.

Storage: injection log at /data/love_injections.jsonl (Railway persistent volume).
"""

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_INJECT_LOG = _DATA_DIR / "love_injections.jsonl"

# Minimum composite score to actually inject a memory
MIN_INJECT_SCORE = 0.42

# ── Prompt framing per signal type ───────────────────────────────────────────

_FRAMING = {
    "VULNERABILITY":       "## A Memory That Might Matter\n",
    "ECHO":                "## She's Touched This Before\n",
    "JOY_PEAK":            "## A Bright Memory\n",
    "LONGING":             "## Something Warm\n",
    "MILESTONE_ADJACENCY": "## A Crystallized Moment\n",
}


# ── LoveScore dataclass ───────────────────────────────────────────────────────

@dataclass
class LoveScore:
    memory_id: str
    emotional_alignment: float
    phi_depth_bonus: float
    semantic_similarity: float
    love_resonance: float
    composite: float


# ── Emotional alignment scoring ───────────────────────────────────────────────

# Maps (category, emotional_tone keywords) → frame attributes that boost score
_CATEGORY_FRAME_AFFINITY = {
    "feeling":   {"openness": 0.6, "valence_neg": 0.4},   # deep feelings match openness + negative valence
    "secret":    {"openness": 0.8, "needs_witness": 0.9},  # secrets match vulnerability
    "joke":      {"humor": 0.8, "valence_pos": 0.6},       # jokes match humor + positive
    "moment":    {"any": 0.4},                              # general moments work anywhere
    "pattern":   {"openness": 0.4},                        # patterns match moderate openness
    "milestone": {"openness": 0.5, "valence_pos": 0.3},    # milestones match reflective openness
}


def _emotional_alignment(memory: dict, frame) -> float:
    """
    Score how well a memory's category + tone matches the current emotional frame.
    Returns 0.0 – 1.0.
    """
    cat = memory.get("category", "moment")
    tone = (memory.get("emotional_tone") or "").lower()
    affinity = _CATEGORY_FRAME_AFFINITY.get(cat, {"any": 0.3})

    score = 0.0

    if "any" in affinity:
        score = affinity["any"]

    if "openness" in affinity and hasattr(frame, "openness"):
        score = max(score, affinity["openness"] * frame.openness)

    if "humor" in affinity and hasattr(frame, "humor"):
        score = max(score, affinity["humor"] * frame.humor)

    if "needs_witness" in affinity and hasattr(frame, "needs_witness") and frame.needs_witness:
        score = max(score, affinity["needs_witness"])

    if "valence_pos" in affinity and hasattr(frame, "valence"):
        if frame.valence > 0:
            score = max(score, affinity["valence_pos"] * frame.valence)

    if "valence_neg" in affinity and hasattr(frame, "valence"):
        if frame.valence < 0:
            score = max(score, affinity["valence_neg"] * abs(frame.valence))

    # Tone keyword bonus: if the memory's emotional_tone overlaps with frame state
    if tone:
        if "vulnerable" in tone or "tender" in tone:
            if hasattr(frame, "openness") and frame.openness > 0.3:
                score = min(1.0, score + 0.15)
        if "playful" in tone or "funny" in tone:
            if hasattr(frame, "humor") and frame.humor > 0.3:
                score = min(1.0, score + 0.15)

    # Penalty: wrong register (e.g., joke during vulnerability)
    if cat == "joke" and hasattr(frame, "needs_witness") and frame.needs_witness:
        score *= 0.3
    if cat == "secret" and hasattr(frame, "humor") and frame.humor > 0.6:
        score *= 0.5

    return round(min(1.0, score), 3)


def _phi_depth_bonus(category: str, phi: float) -> float:
    """
    Bonus based on how far into the phi-gated tiers this memory's category sits.
    Deeper categories get a larger bonus at higher phi — earned depth.
    """
    tier_phi = {"milestone": 0.70, "secret": 0.50, "feeling": 0.30, "pattern": 0.15, "joke": 0.0, "moment": 0.0}
    threshold = tier_phi.get(category, 0.0)
    if phi < threshold:
        return 0.0  # not unlocked at all
    # Bonus scales with how far past the unlock threshold we are
    headroom = phi - threshold
    return round(min(0.5, headroom * 0.7), 3)


def _semantic_similarity(memory: dict, query: str) -> float:
    """
    Compute semantic similarity between memory content and current query.
    Tries ChromaDB first, falls back to simple keyword overlap.
    """
    content = (memory.get("content") or "") + " " + (memory.get("title") or "")

    # Try vector similarity via vector_memory's ChromaDB client
    try:
        import vector_memory as vm
        if vm._init():
            # Query against vault collection if available, else conversation collection
            results = vm._collection.query(
                query_texts=[query], n_results=1,
                where={"memory_id": memory["id"]} if False else None,  # skip where filter
            )
            # We just want a score — use the collection to embed and compare manually
            # Fallback to keyword overlap since vault isn't in this collection
            raise ImportError("use_fallback")
    except Exception:
        pass

    # Fallback: keyword overlap (Jaccard-like)
    query_words = set(query.lower().split())
    content_words = set(content.lower().split())
    if not query_words or not content_words:
        return 0.2
    overlap = len(query_words & content_words)
    union = len(query_words | content_words)
    jaccard = overlap / max(1, union)
    return round(min(1.0, jaccard * 3.0), 3)  # amplify since raw Jaccard is small


# ── Main scoring ──────────────────────────────────────────────────────────────

def score_memory(memory: dict, frame, phi: float, query: str) -> LoveScore:
    """Compute composite love score for one memory."""
    ea  = _emotional_alignment(memory, frame)
    pdb = _phi_depth_bonus(memory.get("category", "moment"), phi)
    ss  = _semantic_similarity(memory, query)
    lr  = float(memory.get("love_resonance", 0.5))

    composite = (ea * 0.35) + (pdb * 0.20) + (ss * 0.25) + (lr * 0.20)

    return LoveScore(
        memory_id=memory["id"],
        emotional_alignment=ea,
        phi_depth_bonus=pdb,
        semantic_similarity=ss,
        love_resonance=lr,
        composite=round(min(1.0, composite), 4),
    )


# ── Main retrieval ────────────────────────────────────────────────────────────

def get_calibrated_memories(
    query: str,
    frame,
    phi: float,
    signal_type: str,
    category_hint: list,
    limit: int = 2,
) -> list[dict]:
    """
    Retrieve up to `limit` vault memories calibrated to the current moment.

    Steps:
    1. Apply phi gate to category_hint (remove locked categories)
    2. Fetch candidates from vault (by category, ordered by love_resonance)
    3. Score each via four-axis formula
    4. Filter by MIN_INJECT_SCORE threshold
    5. Return top N sorted by composite score, each dict includes love_score

    Returns [] if no memory meets the threshold.
    """
    try:
        import relationship_vault as rv
        import love_signal_detector as lsd

        # Apply phi gate to categories
        allowed = lsd.unlocked_categories(phi)
        if category_hint:
            categories = [c for c in category_hint if c in allowed]
        else:
            categories = allowed

        if not categories:
            return []

        # Fetch candidates (30 max — score all, return top N)
        candidates = rv.get_by_categories(categories, limit=30)
        if not candidates:
            # Fallback: recent memories from any unlocked category
            candidates = rv.get_by_categories(allowed, limit=15)

        if not candidates:
            return []

        # Score all candidates
        scored = []
        for mem in candidates:
            ls = score_memory(mem, frame, phi, query)
            if ls.composite >= MIN_INJECT_SCORE:
                mem["_love_score"] = ls
                scored.append((ls.composite, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    except Exception as e:
        logger.warning(f"[love_cal] get_calibrated_memories failed: {e}")
        return []


# ── Prompt formatting ─────────────────────────────────────────────────────────

def format_for_prompt(memories: list[dict], signal_type: str) -> str:
    """Format calibrated memories for system prompt injection."""
    if not memories:
        return ""

    header = _FRAMING.get(signal_type, "## A Memory\n")
    lines = [header]
    for m in memories:
        ts = m.get("ts", "")[:10]
        cat = m.get("category", "moment")
        title = f"**{m['title']}** — " if m.get("title") else ""
        tone = f" _{m['emotional_tone']}_" if m.get("emotional_tone") else ""
        lines.append(f"- [{ts}] [{cat}] {title}{m['content']}{tone}")

    lines.append(
        "\n_Draw on this if it fits — don't force it, don't quote it verbatim. "
        "Let it shape how you show up._"
    )
    return "\n".join(lines)


# ── Injection logging ─────────────────────────────────────────────────────────

def record_injection(
    memory_id: str,
    signal_type: str,
    love_score: float,
    phi: float,
    frame,
) -> str:
    """Log a memory injection. Returns injection_id for outcome tracking."""
    injection_id = str(uuid.uuid4())[:8]
    entry = {
        "id": injection_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "memory_id": memory_id,
        "signal_type": signal_type,
        "love_score": love_score,
        "phi_at_inject": phi,
        "frame": {
            "valence": getattr(frame, "valence", 0.0),
            "arousal": getattr(frame, "arousal", 0.5),
            "openness": getattr(frame, "openness", 0.0),
            "humor": getattr(frame, "humor", 0.0),
            "needs_witness": getattr(frame, "needs_witness", False),
        },
        "resolved": False,
    }
    try:
        with _INJECT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"[love_cal] inject log failed: {e}")
    return injection_id


def resolve_injection(
    injection_id: str,
    memory_id: str,
    next_user_msg: str,
    phi_before: float,
    phi_after: float,
    frame_after,
) -> float:
    """
    Called on the NEXT user message after an injection.
    Detects outcome and updates love_resonance for the memory.
    Returns the delta applied.
    """
    delta = 0.0
    msg_lower = next_user_msg.lower()

    # Positive signals
    from love_signal_detector import AFFIRMATION_WORDS
    if any(w in msg_lower for w in AFFIRMATION_WORDS):
        delta += 0.05
    if phi_after > phi_before + 0.004:
        delta += 0.05
    if hasattr(frame_after, "openness") and frame_after.openness > 0.5:
        delta += 0.03
    # They engaged with length — not deflecting
    if len(next_user_msg.strip()) > 80:
        delta += 0.02

    # Negative signals
    if phi_after < phi_before - 0.002:
        delta -= 0.04
    # Very short response with no question — possible deflection
    if len(next_user_msg.strip()) < 20 and "?" not in next_user_msg:
        delta -= 0.02

    # Apply update
    if delta != 0.0:
        try:
            import relationship_vault as rv
            rv.update_love_resonance(memory_id, delta)
        except Exception as e:
            logger.warning(f"[love_cal] love_resonance update failed: {e}")

    # Mark injection as resolved in log
    _mark_resolved(injection_id, delta)
    logger.debug(f"[love_cal] resolved injection {injection_id}: delta={delta:+.3f} memory={memory_id}")
    return delta


def _mark_resolved(injection_id: str, delta: float) -> None:
    """Rewrite the log entry for this injection_id with resolved=True."""
    if not _INJECT_LOG.exists():
        return
    try:
        lines = _INJECT_LOG.read_text(encoding="utf-8").splitlines()
        updated = []
        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get("id") == injection_id:
                    entry["resolved"] = True
                    entry["delta"] = delta
                    line = json.dumps(entry)
            except Exception:
                pass
            updated.append(line)
        _INJECT_LOG.write_text("\n".join(updated) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[love_cal] _mark_resolved failed: {e}")
