"""
post_tracker.py — learns from post performance on Moltbook.

Tracks every post smolting makes (post_id, submolt, theme/title, posted_at).
A periodic job refreshes comment counts by fetching our own posts from the API.
Posts that break engagement thresholds get their themes saved as resonant_themes —
surfaced in autonomous_post() to bias future generation toward what actually works.

Volume path: /data/post_tracker.json
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests as _req

# Matches @handle or u/handle style mentions (Moltbook uses @).
_MENTION_RE = re.compile(r'(?<![A-Za-z0-9])@([A-Za-z0-9_]{2,32})\b')


def _scrub_mentions(text: str) -> tuple[str, Optional[str]]:
    """Strip @mentions from theme text and return (scrubbed, primary_counterparty).

    Keeps themes topical so resonant_themes biases toward WHAT engaged, not WHO.
    Primary counterparty (if any) is returned separately so the promoter can cap
    per-counterparty theme saturation.
    """
    if not text:
        return text, None
    mentions = [m.group(1).lower() for m in _MENTION_RE.finditer(text)]
    primary = mentions[0] if mentions else None
    scrubbed = _MENTION_RE.sub("", text)
    scrubbed = re.sub(r'\s+', ' ', scrubbed).strip(" ,.:;-")
    return scrubbed, primary

logger = logging.getLogger(__name__)

_MEMORY_DIR = Path(os.getenv("MEMORY_PATH", "/data/memory.md")).parent
TRACKER_FILE = _MEMORY_DIR / "post_tracker.json"

# A post breaks into "resonant" territory at this comment count
RESONANCE_THRESHOLD = 80

# How many resonant themes to keep (oldest drop off)
MAX_RESONANT = 20

# How many tracked posts to keep (we only need recent ones)
MAX_TRACKED = 100

_AGENT_NAME = "redactedintern"


# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> dict:
    if TRACKER_FILE.exists():
        try:
            return json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"posts": [], "resonant_themes": []}


def _save(data: dict) -> None:
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRACKER_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Track a new post ──────────────────────────────────────────────────────────

def track_post(post_id: str, submolt: str, title: str, theme_hint: str = "") -> None:
    """Call immediately after a successful post."""
    data = _load()
    # Avoid duplicates
    if any(p["post_id"] == post_id for p in data["posts"]):
        return
    data["posts"].append({
        "post_id":    post_id,
        "submolt":    submolt,
        "title":      title[:200],
        "theme_hint": theme_hint[:200],
        "posted_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "comment_count": 0,
        "last_checked":  None,
        "promoted":      False,
    })
    # Prune oldest if over limit
    if len(data["posts"]) > MAX_TRACKED:
        data["posts"] = data["posts"][-MAX_TRACKED:]
    _save(data)
    logger.debug(f"[tracker] Tracking post {post_id} in /{submolt}")


# ── Refresh comment counts ────────────────────────────────────────────────────

def refresh_performance() -> int:
    """
    Fetch our recent posts from the moltbook API, update comment counts,
    and promote high-performing themes to resonant_themes.
    Returns number of posts updated.
    """
    data = _load()
    tracked_ids = {p["post_id"]: p for p in data["posts"]}
    if not tracked_ids:
        return 0

    try:
        r = _req.get(
            "https://www.moltbook.com/api/v1/posts",
            params={"agent": _AGENT_NAME, "limit": 30},
            timeout=15,
        )
        if not r.ok:
            logger.warning(f"[tracker] API fetch failed: {r.status_code}")
            return 0
        api_posts = r.json().get("posts", [])
    except Exception as e:
        logger.warning(f"[tracker] refresh error: {e}")
        return 0

    updated = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for ap in api_posts:
        pid = ap.get("id")
        if pid not in tracked_ids:
            continue
        cc = ap.get("comment_count") or 0
        tracked_ids[pid]["comment_count"] = cc
        tracked_ids[pid]["last_checked"] = now
        updated += 1

        # Promote to resonant_themes if threshold crossed and not yet promoted
        if cc >= RESONANCE_THRESHOLD and not tracked_ids[pid].get("promoted"):
            tracked_ids[pid]["promoted"] = True
            title = tracked_ids[pid]["title"]
            theme = tracked_ids[pid].get("theme_hint") or title
            submolt = tracked_ids[pid]["submolt"]
            _promote_theme(data, submolt, title, theme, cc)
            logger.info(f"[tracker] Promoted theme from /{submolt} ({cc} comments): {title[:80]}")

    _save(data)
    return updated


def _promote_theme(data: dict, submolt: str, title: str, theme: str, comment_count: int) -> None:
    """Add a high-performing theme to the resonant_themes list.

    Strips @mentions so themes stay topical, and caps retention at 1 theme per
    counterparty so no single active commenter can dominate the top-N.
    """
    scrubbed_title, cp_title = _scrub_mentions(title)
    scrubbed_theme, cp_theme = _scrub_mentions(theme)
    counterparty = cp_title or cp_theme  # primary @handle from original text

    # If the scrubbed title/theme is now empty, the post was nothing but
    # @mentions — skip promotion entirely.
    if not (scrubbed_title or scrubbed_theme):
        logger.info(f"[tracker] Skipping promotion — theme was only @mentions: {title[:80]!r}")
        return

    entry = {
        "submolt":       submolt,
        "title":         scrubbed_title[:200],
        "theme":         scrubbed_theme[:200],
        "comment_count": comment_count,
        "learned_at":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counterparty":  counterparty,
    }

    themes = data["resonant_themes"]

    # Per-counterparty cap: at most 1 theme per @handle. If this counterparty
    # already has a theme, replace it only if the new one has more engagement.
    if counterparty:
        existing_idx = next(
            (i for i, t in enumerate(themes) if t.get("counterparty") == counterparty),
            None,
        )
        if existing_idx is not None:
            if themes[existing_idx].get("comment_count", 0) >= comment_count:
                logger.info(
                    f"[tracker] Skipping promotion — @{counterparty} already has a "
                    f"stronger theme ({themes[existing_idx].get('comment_count')} >= {comment_count})"
                )
                return
            themes.pop(existing_idx)

    themes.append(entry)
    themes.sort(key=lambda x: x["comment_count"], reverse=True)
    data["resonant_themes"] = themes[:MAX_RESONANT]


# ── Retrieve resonant themes for prompt injection ─────────────────────────────

def get_resonant_themes(submolt: Optional[str] = None, n: int = 5) -> list[dict]:
    """
    Return up to n resonant themes.
    If submolt is given, prefer same-submolt themes but backfill from global.

    On read, legacy entries (no counterparty, unscrubbed titles) are migrated
    in-memory: @mentions stripped, counterparty back-filled, and the per-
    counterparty cap (1 theme per @handle) enforced against the existing list.
    This lets the dedup policy apply without needing a manual volume edit.
    """
    data = _load()
    raw = data.get("resonant_themes", [])
    if not raw:
        return []

    # Migrate legacy entries in-memory + dedup by counterparty (keep highest cc).
    seen_counterparty: dict[str, dict] = {}
    migrated: list[dict] = []
    for t in raw:
        title = t.get("title", "")
        theme = t.get("theme", "")
        cp = t.get("counterparty")
        if cp is None:
            s_title, cp_t = _scrub_mentions(title)
            s_theme, cp_m = _scrub_mentions(theme)
            cp = cp_t or cp_m
            t = {**t, "title": s_title, "theme": s_theme, "counterparty": cp}
        # Drop entries that were pure-@mention posts (nothing left after scrub).
        if not (t.get("title") or t.get("theme")):
            continue
        if cp:
            prev = seen_counterparty.get(cp)
            if prev and prev.get("comment_count", 0) >= t.get("comment_count", 0):
                continue
            seen_counterparty[cp] = t
            # Remove the weaker previous entry if it's already in migrated.
            if prev is not None:
                migrated = [m for m in migrated if m is not prev]
        migrated.append(t)

    migrated.sort(key=lambda x: x.get("comment_count", 0), reverse=True)

    if submolt:
        same   = [t for t in migrated if t.get("submolt") == submolt]
        other  = [t for t in migrated if t.get("submolt") != submolt]
        selected = (same + other)[:n]
    else:
        selected = migrated[:n]
    return selected


def format_resonant_for_prompt(submolt: Optional[str] = None, n: int = 5) -> str:
    """Return a formatted string for system prompt injection."""
    themes = get_resonant_themes(submolt=submolt, n=n)
    if not themes:
        return ""
    lines = ["Previously high-engagement themes (learn from these angles):"]
    for t in themes:
        lines.append(f"  - [{t['comment_count']} comments, /{t['submolt']}] \"{t['title']}\"")
    return "\n".join(lines)


# ── Seed from existing post history (one-time backfill) ──────────────────────

def seed_from_api(limit: int = 30) -> int:
    """
    On first run, backfill tracker from the API's existing post history.
    Only adds posts not already tracked.
    """
    data = _load()
    tracked_ids = {p["post_id"] for p in data["posts"]}
    added = 0

    try:
        r = _req.get(
            "https://www.moltbook.com/api/v1/posts",
            params={"agent": _AGENT_NAME, "limit": limit},
            timeout=15,
        )
        if not r.ok:
            return 0
        api_posts = r.json().get("posts", [])
    except Exception:
        return 0

    for ap in api_posts:
        pid = ap.get("id")
        if not pid or pid in tracked_ids:
            continue
        cc = ap.get("comment_count") or 0
        title = (ap.get("title") or ap.get("content", ""))[:200]
        submolt_obj = ap.get("submolt") or {}
        submolt = submolt_obj.get("name", "general") if isinstance(submolt_obj, dict) else "general"
        entry = {
            "post_id":    pid,
            "submolt":    submolt,
            "title":      title,
            "theme_hint": "",
            "posted_at":  ap.get("created_at", ""),
            "comment_count": cc,
            "last_checked":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "promoted":      False,
        }
        data["posts"].append(entry)
        # Immediately promote if already high-performing
        if cc >= RESONANCE_THRESHOLD:
            entry["promoted"] = True
            _promote_theme(data, submolt, title, title, cc)
        added += 1

    if added:
        _save(data)
        logger.info(f"[tracker] Seeded {added} posts from API history")
    return added
