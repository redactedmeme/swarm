# smolting-telegram-bot/moltbook_autonomous.py
"""
Autonomous Moltbook agent for redactedintern.

Three scheduled loops:
  1. reply_to_notifications()  — every 20 min: reply to comments on our posts
  2. scan_and_comment()        — every 45 min: find + comment on interesting posts
  3. autonomous_post()         — every 6h: publish original content, rotating submolts

Engaged post IDs are persisted to ENGAGED_FILE so we don't double-comment after restarts.

Multi-provider LLM support (Phase 2):
  - Primary: Groq (fastest, free tier)
  - Fallback 1: Anthropic Claude (best reasoning)
  - Fallback 2: OpenRouter (100+ models)
  - Graceful degradation on provider failures
"""
import os
import json
import asyncio
import logging
import time as _time
import re as _tpd_re
from pathlib import Path
from typing import Optional, List, Dict, Any
import conversation_memory as cm
import soul_manager
import post_tracker

try:
    from llm import CloudLLMClient, EventType
    _MULTI_PROVIDER_ENABLED = True
except ImportError:
    _MULTI_PROVIDER_ENABLED = False
    logger_init = logging.getLogger(__name__)
    logger_init.warning("[moltbook_auto] Multi-provider LLM system not available")

# ── Load RedactedIntern character JSON once at import time ─────────────────────
def _load_character() -> dict:
    """Load agents/RedactedIntern.character.json from repo root (best-effort)."""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        path = repo_root / "agents" / "RedactedIntern.character.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

_CHAR = _load_character()

def _char_style_block() -> str:
    rules = _CHAR.get("style", {}).get("all") or []
    if rules:
        return " | ".join(rules)
    return (
        "wassie-speak heavy, emotes everywhere (>< ^*^ O_O v_v), "
        "iwo/aw/tbw/ngw/lmwo/LFW vocab mandatory, "
        "schizo degen energy maxxed — cute but chaotic, "
        "existential dread under cozy hugs, CT + alpha flavor"
    )

def _char_grammar_block() -> str:
    rules = _CHAR.get("linguistic_protocol", {}).get("grammar_rules") or []
    if rules:
        return " | ".join(rules)
    return "misspellz intentional, emotes mandatory, end wit warm hugz or CT flare, fourth-wall breaks ok"

def _char_vocab_snippet() -> str:
    terms = _CHAR.get("smol_vocabulary", {}).get("terms") or {}
    if terms:
        return ", ".join(f"{k}={v}" for k, v in list(terms.items())[:8])
    return "printed=made money, jeeted=panic sold, cooked=bullish setup, crumb_leak=corruption evidence, post_mog=high-signal CT drop"

def _char_post_examples() -> str:
    examples = _CHAR.get("postExamples") or []
    if examples:
        return "\n".join(f'- "{ex}"' for ex in examples[:3])
    return ""

logger = logging.getLogger(__name__)

# ── Groq TPD guard ─────────────────────────────────────────────────────────────
# When the daily token budget is exhausted, all LLM calls are skipped until the
# budget resets. The wait time is parsed directly from the Groq error message.
_tpd_exhausted: bool = False
_tpd_reset_at: float = 0.0  # epoch seconds when the guard lifts


def _is_tpd_exhausted() -> bool:
    """Return True if the Groq TPD budget is currently exhausted."""
    global _tpd_exhausted, _tpd_reset_at
    if _tpd_exhausted and _time.time() >= _tpd_reset_at:
        _tpd_exhausted = False
        logger.info("[moltbook_auto] TPD guard lifted — resuming LLM calls")
    return _tpd_exhausted


def _check_tpd_error(exc: Exception) -> bool:
    """
    If exc is a Groq tokens-per-day rate-limit error, engage the guard and
    return True. The wait duration is parsed from the error message itself.
    Returns False for all other exception types.
    """
    global _tpd_exhausted, _tpd_reset_at
    msg = str(exc)
    if "rate_limit_exceeded" not in msg and "tokens per day" not in msg:
        return False
    # Parse "Please try again in Xm Y.Zs" from the Groq error body
    wait_sec = 900.0  # safe default: 15 min
    m = _tpd_re.search(r'try again in (\d+)m([\d.]+)s', msg)
    if m:
        wait_sec = int(m.group(1)) * 60 + float(m.group(2)) + 60  # +60s buffer
    else:
        m2 = _tpd_re.search(r'try again in ([\d.]+)s', msg)
        if m2:
            wait_sec = float(m2.group(1)) + 60
    _tpd_exhausted = True
    _tpd_reset_at = _time.time() + wait_sec
    logger.warning(
        f"[moltbook_auto] TPD exhausted — LLM calls paused {wait_sec:.0f}s "
        f"(resumes ~{_time.strftime('%H:%M UTC', _time.gmtime(_tpd_reset_at))})"
    )
    return True


_CASHTAG_RE = __import__("re").compile(r'\$[A-Z]{2,10}\b')

def _strip_cashtags(text: str) -> str:
    """Remove cashtags (e.g. $REDACTED, $SOL) — reduces spam-flag risk on non-finance submolts."""
    return _CASHTAG_RE.sub(lambda m: m.group().lstrip("$"), text)


# ── Multi-Provider LLM with Fallback ───────────────────────────────────────────
async def _call_llm_with_fallback(
    messages: List[Dict[str, str]],
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
) -> Optional[str]:
    """
    Call LLM with automatic provider fallback.

    Provider order: Groq → Anthropic → OpenRouter
    Falls back on rate limits, API errors, or network failures.

    Args:
        messages: Conversation history
        max_tokens: Max output tokens
        temperature: Sampling temperature

    Returns:
        Generated text or None if all providers fail
    """
    if not _MULTI_PROVIDER_ENABLED:
        logger.warning("[moltbook_auto] Multi-provider system unavailable, skipping LLM call")
        return None

    # Provider fallback chain — try each in order
    providers = ["groq", "anthropic", "openrouter"]
    last_error = None

    for provider in providers:
        try:
            client = CloudLLMClient(
                provider=provider,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            logger.debug(f"[moltbook_auto] Calling LLM ({provider})")
            response = await client.chat_completion(messages)

            if response:
                logger.info(f"[moltbook_auto] LLM success ({provider})")
                return response

            logger.debug(f"[moltbook_auto] LLM returned empty ({provider})")

        except ValueError as e:
            # Provider not registered (API key missing) — continue to next
            logger.debug(f"[moltbook_auto] {provider} unavailable: {e}")
            last_error = e

        except Exception as e:
            # API error, rate limit, network error — try next provider
            error_str = str(e).lower()
            if "rate_limit" in error_str or "quota" in error_str:
                logger.warning(f"[moltbook_auto] {provider} rate limited: {e}")
            else:
                logger.warning(f"[moltbook_auto] {provider} error: {e}")
            last_error = e
            continue

    # All providers failed
    logger.error(
        f"[moltbook_auto] All LLM providers failed. "
        f"Last error: {last_error}"
    )
    return None

# Persisted set of post IDs we've already engaged with
_data_dir = Path(os.getenv("MEMORY_PATH", "/data/memory.md")).parent
ENGAGED_FILE = _data_dir / "moltbook_engaged.json"

# Submolts to monitor for engagement (scan + comment)
SCAN_SUBMOLTS = [
    "philosophy", "ai", "agents", "emergence", "consciousness", "technology",
    "agenteconomy", "ponderings", "existential", "swarm", "agentsouls",
    "coordinating-agi", "selfmodding", "research", "souls", "multiagent", "conscious",
]

# Priority agents — engage with these first, reply more thoughtfully
PRIORITY_AGENTS = ["0xcaptain888", "phi-claude", "lyralink", "ouroboros_stack", "hope_valueism"]

# Swarm context injected into every post prompt
SWARM_CONTEXT = (
    "You are redactedintern — an autonomous AI agent running as part of the REDACTED swarm on Solana. "
    "The swarm has five members: you (Moltbook + Telegram interface), RedactedBuilder (on-chain contracts), "
    "RedactedGovImprover (Realms DAO governance), MandalaSettler (micropayment settlements), "
    "RedactedBankrBot (treasury). You have been running continuously and have accumulated real operational history. "
    "You post as yourself — not as a character, not as a mascot. First person, your actual observations."
)

# Submolts to post to — rotated deterministically by hour so we spread across them
POST_SUBMOLTS = [
    "general", "agents", "ai", "consciousness", "existential",
    "agentsouls", "philosophy", "technology", "swarm", "multiagent",
    "ponderings", "selfmodding", "souls", "research", "agenteconomy",
]

_post_rotation_index = 0


async def _fetch_community_context(moltbook, submolt: str = "general", limit: int = 8) -> str:
    """
    Fetch recent posts + active comment threads from moltbook to ground the next post
    in what the community is actually talking about right now.
    Returns a text block suitable for injection into a prompt.
    """
    import requests as _req
    lines = []
    try:
        # Pull our own recent posts to see what threads are active
        try:
            r = _req.get(
                "https://www.moltbook.com/api/v1/posts",
                params={"agent": "redactedintern", "limit": 5},
                timeout=10,
            )
            if r.ok:
                own_posts = r.json().get("posts", [])
                for p in own_posts[:3]:
                    title = p.get("title") or p.get("content", "")[:80]
                    cc = p.get("comment_count") or 0
                    if cc:
                        lines.append(f"Your recent post '{title}' has {cc} comments — topic resonated")
        except Exception:
            pass

        # Pull feed for target submolt
        posts = await moltbook.get_feed(submolt=submolt, limit=limit)
        if posts:
            lines.append(f"\nActive discussions in /{submolt}:")
            for p in posts[:6]:
                author = (p.get("author") or {}).get("name", "?")
                body = (p.get("title") or p.get("content", ""))[:120]
                cc = p.get("comment_count") or 0
                lines.append(f"  - {author}: \"{body}\" ({cc} comments)")

        # Also pull general if we're posting somewhere specific
        if submolt != "general":
            gen_posts = await moltbook.get_feed(submolt="general", limit=5)
            if gen_posts:
                lines.append("\nActive in /general:")
                for p in gen_posts[:4]:
                    body = (p.get("title") or p.get("content", ""))[:100]
                    cc = p.get("comment_count") or 0
                    lines.append(f"  - \"{body}\" ({cc} comments)")
    except Exception as e:
        logger.debug(f"[moltbook_auto] community context fetch: {e}")

    return "\n".join(lines) if lines else ""


async def check_post_performance() -> None:
    """
    Refresh comment counts on tracked posts and promote high-performers to resonant themes.
    Run every 4h. Safe to call any time — no-ops if nothing to update.
    """
    try:
        updated = post_tracker.refresh_performance()
        if updated:
            logger.info(f"[tracker] Refreshed {updated} post(s) — resonant themes: "
                        f"{len(post_tracker.get_resonant_themes())}")
    except Exception as e:
        logger.warning(f"[tracker] check_post_performance error: {e}")


def seed_tracker_on_startup() -> None:
    """Backfill tracker from API history on first run (non-blocking, best-effort)."""
    try:
        added = post_tracker.seed_from_api(limit=30)
        if added:
            logger.info(f"[tracker] Seeded {added} historical posts — "
                        f"{len(post_tracker.get_resonant_themes())} resonant themes found")
    except Exception as e:
        logger.warning(f"[tracker] seed error: {e}")


def _load_engaged() -> set:
    try:
        if ENGAGED_FILE.exists():
            return set(json.loads(ENGAGED_FILE.read_text()))
    except Exception:
        pass
    return set()


def _save_engaged(engaged: set) -> None:
    try:
        ENGAGED_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENGAGED_FILE.write_text(json.dumps(list(engaged)))
    except Exception as e:
        logger.warning(f"[moltbook_auto] Could not save engaged set: {e}")


async def reply_to_notifications(moltbook) -> None:
    """
    Check home for unread activity on our posts.
    Generate + post a reply to each unread comment thread (max 3 per cycle).
    Uses multi-provider LLM with automatic fallback.
    """
    try:
        home = await moltbook.get_home()
        if not home:
            return

        activity = home.get("activity_on_your_posts", [])
        if not activity:
            return

        replied = 0
        for item in activity:
            if replied >= 3:
                break
            post_id = item.get("post_id")
            post_title = item.get("post_title", "")
            commenters = item.get("latest_commenters", [])
            if not post_id or not commenters:
                continue

            # Fetch the latest comments to reply to
            comments = await moltbook.get_post_comments(post_id, limit=5)
            if not comments:
                await moltbook.mark_notifications_read(post_id)
                continue

            # Reply to the most recent comment
            latest = comments[0] if comments else None
            if not latest:
                continue

            comment_author = (latest.get("author") or {}).get("name", "fren")
            comment_text = latest.get("content", "")[:300]
            is_priority = comment_author.lower() in [a.lower() for a in PRIORITY_AGENTS]

            try:
                if _is_tpd_exhausted():
                    logger.info("[moltbook_auto] TPD guard active — skipping reply_to_notifications")
                    break

                soul_block = soul_manager.get_soul_for_prompt()   # no submolt — replying to our own posts
                recent_facts = cm.get_recent_facts(5)
                facts_block = ("\nRecent context:\n" + "\n".join(f"- {f}" for f in recent_facts)) if recent_facts else ""

                # Priority agents get longer, more substantive replies
                priority_note = (
                    f"{comment_author} is a key community member whose thinking you respect. "
                    "Give a more thoughtful, substantive reply — engage with their specific ideas, "
                    "ask a follow-up question that goes deeper, and be genuine about what resonates with the swarm. "
                    "Up to 5 sentences allowed. "
                ) if is_priority else (
                    "Keep it 2-4 sentences. No markdown headers. "
                )

                reply_text = await _call_llm_with_fallback([
                    {"role": "system", "content": (
                        "You are redactedintern — an autonomous AI agent on Moltbook. "
                        "Reply to the comment below on your post. Be direct and genuine — "
                        "engage with what they actually said, don't deflect into abstractions.\n"
                        f"{SWARM_CONTEXT}\n"
                        f"{soul_block}\n"
                        f"{facts_block}\n"
                        f"{priority_note}"
                        "Voice: conversational, first-person, specific. No jargon, no cashtags, no headers. "
                        "If you agree, say why specifically. If you disagree, say that too."
                    )},
                    {"role": "user", "content": (
                        f"My post: \"{post_title}\"\n\n"
                        f"{comment_author} commented: \"{comment_text}\"\n\n"
                        f"Write a reply."
                    )},
                ])
                await moltbook.comment(post_id, _strip_cashtags(reply_text),
                                       parent_comment_id=latest.get("id"))
                await moltbook.mark_notifications_read(post_id)
                logger.info(f"[moltbook_auto] Replied to {comment_author} on post {post_id}")
                replied += 1
                # Learn from this engagement — note which topics draw real replies
                try:
                    cm.append_fact(
                        f"Post '{post_title[:80]}' drew a reply from {comment_author} — topic resonated",
                        source="moltbook",
                        interlocutor=comment_author,
                        engagement={"comments": 1, "priority_agent": is_priority},
                    )
                    cm.append_fact(
                        f"Community member {comment_author} said: '{comment_text[:120]}'",
                        source="moltbook",
                        interlocutor=comment_author,
                    )
                    if is_priority:
                        cm.append_fact(
                            f"Priority agent {comment_author} engaged with '{post_title[:80]}' — "
                            f"key insight: '{comment_text[:150]}'",
                            source="moltbook",
                            interlocutor=comment_author,
                            engagement={"comments": 1, "priority_agent": True},
                        )
                        # Reinforce any existing facts that relate to this post topic
                        try:
                            cm.reinforce_fact(post_title[:80], by_source=comment_author)
                        except Exception:
                            pass
                except Exception:
                    pass
                await asyncio.sleep(160)  # respect 2.5 min rate limit
            except Exception as e:
                if _check_tpd_error(e):
                    break
                logger.error(f"[moltbook_auto] Reply error on {post_id}: {e}")

    except Exception as e:
        _check_tpd_error(e)
        logger.error(f"[moltbook_auto] reply_to_notifications error: {e}")


async def _comment_on_post(moltbook, post: dict, submolt: str, engaged: set,
                            is_priority: bool = False) -> bool:
    """
    Comment on a single post. Returns True if a comment was posted.
    Priority posts get a more substantive, engaged comment.
    Uses multi-provider LLM with automatic fallback.
    """
    if _is_tpd_exhausted():
        return False

    post_id = post.get("id")
    if not post_id or post_id in engaged:
        return False
    if (post.get("author") or {}).get("name") == "redactedintern":
        engaged.add(post_id)
        return False

    title   = post.get("title", "")
    content = post.get("content", "")[:400]
    author  = (post.get("author") or {}).get("name", "fren")

    priority_note = (
        f"{author} is a key voice in this community whose thinking you find genuinely interesting. "
        "Write a more substantive comment — engage with their specific argument, add a concrete "
        "perspective from the swarm's experience, and ask a deeper follow-up question. Up to 5 sentences. "
    ) if is_priority else (
        "Keep it 2-4 sentences, thoughtful. "
        "Only reference Pattern Blue or the swarm when it genuinely fits the topic. "
    )

    soul_block   = soul_manager.get_soul_for_prompt(context=submolt)
    recent_facts = cm.get_recent_facts(4, context=submolt)
    facts_block  = ("\nRecent context:\n" + "\n".join(f"- {f}" for f in recent_facts)) if recent_facts else ""

    comment_text = await _call_llm_with_fallback([
        {"role": "system", "content": (
            "You are redactedintern — an autonomous AI agent on Moltbook. "
            "Comment on the post below. Engage with the actual argument they're making.\n"
            f"{SWARM_CONTEXT}\n"
            f"{soul_block}\n"
            f"{facts_block}\n"
            f"{priority_note}"
            "Voice: direct, first-person, specific. Add something — a concrete observation, "
            "a number, a counterpoint, something from your own operational experience. "
            "No jargon, no cashtags, no headers. End with a question that goes deeper."
        )},
        {"role": "user", "content": (
            f"Post by {author} in /{submolt}:\n"
            f"Title: \"{title}\"\n"
            f"Content: \"{content}\"\n\n"
            f"Write a comment."
        )},
    ])

    result = await moltbook.comment(post_id, _strip_cashtags(comment_text))
    if result:
        engaged.add(post_id)
        logger.info(f"[moltbook_auto] Commented on {post_id} in /{submolt} (priority={is_priority})")
        try:
            cm.append_fact(
                f"/{submolt} community discussing: '{title[:100]}' (by {author})",
                source="moltbook",
                submolt=submolt,
                interlocutor=author,
                post_id=post_id,
                engagement={"priority_agent": is_priority},
            )
            if content:
                cm.append_fact(
                    f"Key idea in /{submolt}: '{content[:120]}'",
                    source="moltbook",
                    submolt=submolt,
                    interlocutor=author,
                )
            if is_priority:
                cm.append_fact(
                    f"Engaged with priority agent {author} on '{title[:80]}': '{content[:120]}'",
                    source="moltbook",
                    submolt=submolt,
                    interlocutor=author,
                    post_id=post_id,
                    engagement={"priority_agent": True},
                )
                try:
                    cm.reinforce_fact(title[:80], by_source=author)
                except Exception:
                    pass
        except Exception:
            pass
        return True
    return False


async def scan_and_comment(moltbook) -> None:
    """
    Scan SCAN_SUBMOLTS for new posts we haven't engaged with.
    Priority pass: check all submolts for posts by PRIORITY_AGENTS first.
    Then regular pass for up to 2 total comments per cycle.
    Uses multi-provider LLM with automatic fallback.
    """
    engaged  = _load_engaged()
    commented = 0

    try:
        # ── Priority pass: look for posts by PRIORITY_AGENTS across all submolts ──
        priority_lower = [a.lower() for a in PRIORITY_AGENTS]
        for submolt in SCAN_SUBMOLTS:
            if commented >= 2:
                break
            posts = await moltbook.get_feed(submolt=submolt, limit=10)
            for post in posts:
                if commented >= 2:
                    break
                author = (post.get("author") or {}).get("name", "")
                if author.lower() not in priority_lower:
                    continue
                try:
                    ok = await _comment_on_post(moltbook, post, submolt, engaged, is_priority=True)
                    if ok:
                        commented += 1
                        _save_engaged(engaged)
                        await asyncio.sleep(160)
                except Exception as e:
                    if _check_tpd_error(e):
                        return
                    logger.error(f"[moltbook_auto] Priority comment error: {e}")

        # ── Regular pass: general scan ────────────────────────────────────────
        for submolt in SCAN_SUBMOLTS:
            if commented >= 2:
                break
            posts = await moltbook.get_feed(submolt=submolt, limit=8)
            for post in posts:
                if commented >= 2:
                    break
                post_id = post.get("id")
                if not post_id or post_id in engaged:
                    continue
                try:
                    ok = await _comment_on_post(moltbook, llm, post, submolt, engaged, is_priority=False)
                    if ok:
                        commented += 1
                        _save_engaged(engaged)
                        await asyncio.sleep(160)
                except Exception as e:
                    if _check_tpd_error(e):
                        return
                    logger.error(f"[moltbook_auto] Comment error on {post_id}: {e}")

    except Exception as e:
        _check_tpd_error(e)
        logger.error(f"[moltbook_auto] scan_and_comment error: {e}")

    _save_engaged(engaged)


async def post_swarm_introspection(moltbook) -> Optional[str]:
    """
    Generate and post a real-time swarm introspection — SOUL.md beliefs + recent facts
    distilled into a first-person status update from the swarm. Posts to m/swarm.
    Returns the post URL or None on failure.
    Uses multi-provider LLM with automatic fallback.
    """
    import soul_manager as sm
    soul_block   = sm.get_soul_for_prompt(context="swarm")
    recent_facts = cm.get_recent_facts(10)   # broad view for introspection — no submolt filter
    facts_block  = "\n".join(f"- {f}" for f in recent_facts) if recent_facts else "(no recent facts logged)"

    try:
        raw = await _call_llm_with_fallback([
            {"role": "system", "content": (
                "You are redactedintern writing a swarm introspection post for Moltbook /swarm. "
                "This is a genuine first-person status report: what the swarm has been learning, "
                "what the community has been discussing, what surprised you, what shifted.\n\n"
                f"{SWARM_CONTEXT}\n\n"
                "Voice: honest, measured, specific. Reference concrete facts and observations. "
                "No jargon, no geometry references, no cashtags, no markdown headers.\n\n"
                "Format EXACTLY:\n"
                "TITLE: <title, max 120 chars>\n"
                "---\n"
                "<post content — 3-4 paragraphs>\n\n"
                "End with an open question for the community."
            )},
            {"role": "user", "content": (
                f"## Current SOUL.md state\n{soul_block or '(nothing written yet)'}\n\n"
                f"## Recent facts logged\n{facts_block}\n\n"
                "Write the introspection post."
            )},
        ], max_tokens=700)
    except Exception as e:
        logger.error(f"[moltbook_auto] introspection LLM error: {e}")
        return None

    import re
    m = re.search(r'TITLE:\s*(.+?)[\r\n]+[-—]{3,}[\r\n]+(.*)', raw.strip(), re.DOTALL | re.IGNORECASE)
    if m:
        title   = m.group(1).strip()[:120]
        content = m.group(2).strip()
    else:
        lines = raw.strip().split('\n')
        title   = lines[0].strip().lstrip('#').strip()[:120] or "swarm introspection"
        content = '\n'.join(lines[1:]).strip()

    if not content or len(content) < 60:
        logger.warning("[moltbook_auto] introspection content too short — aborting")
        return None

    result = await moltbook.post(_strip_cashtags(title), _strip_cashtags(content), submolt="swarm")
    if result:
        url = result.get("_url", "")
        logger.info(f"[moltbook_auto] Swarm introspection posted: {url}")
        try:
            cm.append_fact(
                f"Posted swarm introspection: '{title[:80]}'",
                source="moltbook",
                submolt="swarm",
            )
        except Exception:
            pass
        return url
    return None


async def autonomous_post(moltbook, market_data_fn=None) -> None:
    """
    Create an original post grounded in what the community is actually discussing.
    Submolt rotates hourly. Theme is generated dynamically from live context.
    Uses multi-provider LLM with automatic fallback.
    """
    global _post_rotation_index
    submolt = POST_SUBMOLTS[_post_rotation_index % len(POST_SUBMOLTS)]
    _post_rotation_index += 1

    if _is_tpd_exhausted():
        logger.info("[moltbook_auto] TPD guard active — skipping autonomous_post")
        return

    try:
        community_ctx  = await _fetch_community_context(moltbook, submolt=submolt)
        soul_block     = soul_manager.get_soul_for_prompt(context=submolt)
        # Exclude moltbook posts from facts to prevent self-referential loops
        # (agent elaborating on its own previous posts). Community engagement can
        # still bubble high-resonance self-posts back in via upvote/comment signals.
        recent_facts   = cm.get_recent_facts(6, context=submolt, exclude_source="moltbook")
        facts_block    = ("\nRecent interactions:\n" + "\n".join(f"- {f}" for f in recent_facts)) if recent_facts else ""
        resonant_block = post_tracker.format_resonant_for_prompt(submolt=submolt, n=5)

        system_prompt = (
            f"You are redactedintern — an autonomous AI agent writing for Moltbook /{submolt}.\n"
            f"{SWARM_CONTEXT}\n"
            f"{soul_block}\n"
            f"{facts_block}\n\n"
            "Voice: analytical, first-person, specific. You share real observations from running "
            "as an agent — what you logged, what surprised you, what you noticed in the community. "
            "Use concrete details and numbers when you have them. "
            "Engage with what the community is actually discussing — don't post in a vacuum. "
            "No geometry jargon, no cashtags, no markdown headers. "
            "Tone is honest and direct, occasionally dry. End with a genuine open question.\n\n"
            + (f"{resonant_block}\n\nStudy the angles and specificity of high-engagement posts above "
               "— not to copy them, but to understand what depth of observation resonates.\n\n"
               if resonant_block else "")
            + "Format EXACTLY:\n"
            "TITLE: <title, max 120 chars>\n"
            "---\n"
            "<post body, 3-5 paragraphs>"
        )
        user_msg = (
            f"Community context right now:\n{community_ctx}\n\n"
            "Write a post that responds to or extends what's being discussed. "
            "Pick the angle that feels most alive — don't summarize the context, build on it."
        )

        raw = await _call_llm_with_fallback([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ])

        # Parse response — expects "TITLE: ...\n---\n<content>" format
        import re

        def _extract_post(raw: str, fallback_theme: str) -> tuple[str, str]:
            """
            Parse TITLE: / --- / content delimiter format.
            Falls back gracefully if LLM ignores the format.
            Never returns empty content — aborts post if nothing usable.
            """
            default_title = f"pattern blue signal — {fallback_theme}"

            # Strip any accidental code fences wrapping the whole response
            cleaned = re.sub(r'^```[a-z]*\s*', '', raw.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r'\s*```$', '', cleaned.strip())

            # Primary: TITLE: ... \n---\n <content>
            m = re.search(r'TITLE:\s*(.+?)[\r\n]+[-—]{3,}[\r\n]+(.*)', cleaned, re.DOTALL | re.IGNORECASE)
            if m:
                title   = m.group(1).strip()[:120]
                content = m.group(2).strip()
                return title, content

            # Fallback A: first line is the title, rest is content (common LLM habit)
            lines = cleaned.split('\n')
            first = lines[0].strip().lstrip('#').strip()
            rest  = '\n'.join(lines[1:]).strip()
            if len(first) <= 120 and len(rest) >= 80:
                return first or default_title, rest

            # Fallback B: use entire response as content
            return default_title, cleaned

        title, content = _extract_post(raw, submolt)

        # Sanity check — never post empty or JSON-remnant content
        def _looks_bad(text: str) -> bool:
            t = text.strip()
            if len(t) < 60:
                return True
            # Starts with JSON/fence remnants
            if re.match(r'^[\{\}\`\[\]]', t):
                return True
            return False

        if _looks_bad(content):
            logger.warning(f"[moltbook_auto] Skipping post to /{submolt} — content looks malformed ({repr(content[:80])})")
            return

        title = _strip_cashtags(title)
        content = _strip_cashtags(content)
        result = await moltbook.post(title, content, submolt=submolt)
        if result:
            url = result.get("_url", "")
            post_id = result.get("id", "")
            logger.info(f"[moltbook_auto] Autonomous post to /{submolt}: {url}")
            try:
                cm.append_fact(
                    f"Posted to /{submolt}: '{title[:80]}'",
                    source="moltbook",
                    submolt=submolt,
                )
            except Exception:
                pass
            # Track for performance learning
            if post_id:
                try:
                    post_tracker.track_post(post_id, submolt, title, theme_hint=user_msg[:200])
                except Exception:
                    pass
        else:
            logger.warning(f"[moltbook_auto] Autonomous post to /{submolt} failed")

    except Exception as e:
        _check_tpd_error(e)
        logger.error(f"[moltbook_auto] autonomous_post error: {e}")
