# smolting-telegram-bot/x_client.py
"""
X (Twitter) API v2 client — direct OAuth 1.0a via tweepy.

Credentials (set in Railway env vars):
  X_CONSUMER_KEY, X_CONSUMER_SECRET
  X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

Functions:
  post_tweet(text)                   — post a single tweet, returns tweet ID
  search_alpha(query, max_results)   — search recent tweets (Basic tier required)
  get_ct_alpha(query, max_results)   — convenience: crypto/CT alpha search
"""
import os
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import tweepy
    _TWEEPY_OK = True
except ImportError:
    _TWEEPY_OK = False
    logger.warning("tweepy not installed — X client disabled. Add tweepy to requirements.txt")


_me_id_cache: Optional[str] = None


def _make_client() -> Optional["tweepy.Client"]:
    """Build a tweepy v2 Client from env vars. Returns None if any credential is missing."""
    if not _TWEEPY_OK:
        return None
    ck  = os.getenv("X_CONSUMER_KEY")
    cs  = os.getenv("X_CONSUMER_SECRET")
    at  = os.getenv("X_ACCESS_TOKEN")
    ats = os.getenv("X_ACCESS_TOKEN_SECRET")
    if not all([ck, cs, at, ats]):
        logger.warning("X API: one or more credentials missing — check Railway env vars")
        return None
    return tweepy.Client(
        consumer_key=ck,
        consumer_secret=cs,
        access_token=at,
        access_token_secret=ats,
        wait_on_rate_limit=True,
    )


async def _get_me_id() -> Optional[str]:
    """Return the authenticated user's ID (cached after first call)."""
    global _me_id_cache
    if _me_id_cache:
        return _me_id_cache
    client = _make_client()
    if not client:
        return None
    try:
        resp = await asyncio.to_thread(client.get_me)
        _me_id_cache = str(resp.data.id)
        return _me_id_cache
    except Exception as e:
        logger.error(f"X get_me error: {e}")
        return None


async def post_tweet(text: str, reply_to: Optional[str] = None) -> Optional[str]:
    """
    Post a tweet via X API v2. Returns tweet ID string on success, None on failure.
    text is truncated to 280 chars automatically.
    """
    client = _make_client()
    if not client:
        return None
    text = text[:280]
    kwargs: dict = {"text": text}
    if reply_to:
        kwargs["reply"] = {"in_reply_to_tweet_id": reply_to}
    try:
        resp = await asyncio.to_thread(client.create_tweet, **kwargs)
        tweet_id = str(resp.data["id"])
        logger.info(f"X: posted tweet {tweet_id}")
        return tweet_id
    except Exception as e:
        logger.error(f"X post_tweet error: {e}")
        return None


async def like_tweet(tweet_id: str) -> bool:
    """Like a tweet. Returns True on success."""
    client = _make_client()
    if not client:
        return False
    me_id = await _get_me_id()
    if not me_id:
        return False
    try:
        await asyncio.to_thread(client.like, tweet_id=int(tweet_id))
        logger.info(f"X: liked tweet {tweet_id}")
        return True
    except Exception as e:
        logger.error(f"X like_tweet error: {e}")
        return False


async def retweet(tweet_id: str) -> bool:
    """Retweet a tweet. Returns True on success."""
    client = _make_client()
    if not client:
        return False
    me_id = await _get_me_id()
    if not me_id:
        return False
    try:
        await asyncio.to_thread(client.retweet, tweet_id=int(tweet_id))
        logger.info(f"X: retweeted tweet {tweet_id}")
        return True
    except Exception as e:
        logger.error(f"X retweet error: {e}")
        return False


async def search_alpha(
    query: str,
    max_results: int = 10,
) -> Optional[list]:
    """
    Search recent tweets (last 7 days).
    Requires X API Basic tier ($100/mo) — returns None on free tier 403.

    Returns list of dicts: {id, text, created_at, metrics} or None on error.
    max_results must be 10–100.
    """
    client = _make_client()
    if not client:
        return None
    max_results = max(10, min(100, max_results))
    try:
        resp = await asyncio.to_thread(
            client.search_recent_tweets,
            query=query,
            max_results=max_results,
            tweet_fields=["created_at", "author_id", "public_metrics"],
        )
        if not resp.data:
            return []
        return [
            {
                "id":         str(t.id),
                "text":       t.text,
                "created_at": str(t.created_at),
                "metrics":    t.public_metrics or {},
            }
            for t in resp.data
        ]
    except tweepy.Forbidden:
        logger.warning("X search_alpha: 403 Forbidden — Basic tier required for search")
        return None
    except Exception as e:
        logger.error(f"X search_alpha error: {e}")
        return None


# Default CT / Solana alpha query
_CT_QUERY = (
    "($REDACTED OR #REDACTED OR solana alpha OR SOL meme OR CT alpha) "
    "-is:retweet -is:reply lang:en"
)


async def get_ct_alpha(query: str = None, max_results: int = 20) -> Optional[list]:
    """
    Convenience: search CT / Solana alpha signals.
    Falls back to default query targeting $REDACTED + Solana ecosystem.
    """
    return await search_alpha(query or _CT_QUERY, max_results=max_results)


def format_alpha_tweets(tweets: list, limit: int = 5) -> str:
    """Format a list of tweet dicts into a compact LLM-readable string."""
    if not tweets:
        return "(no recent tweets found)"
    lines = []
    for t in tweets[:limit]:
        m = t.get("metrics", {})
        likes    = m.get("like_count", 0)
        retweets = m.get("retweet_count", 0)
        text     = t["text"].replace("\n", " ")[:200]
        lines.append(f"  [{likes}♥ {retweets}RT] {text}")
    return "\n".join(lines)
