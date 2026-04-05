# smolting-telegram-bot/clawnx_integration.py
"""
X/Twitter integration — thin wrapper over x_client.py (X API v2, OAuth 1.0a).
Credentials: X_CONSUMER_KEY, X_CONSUMER_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
"""
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class ClawnXClient:
    """X/Twitter client — delegates to x_client (X API v2)."""

    def __init__(self):
        import os
        self._ready = bool(os.environ.get("X_CONSUMER_KEY"))
        if not self._ready:
            logger.warning("X API credentials not set (X_CONSUMER_KEY). Posting disabled.")

    async def post_tweet(self, text: str, reply_to: Optional[str] = None,
                         quote_id: Optional[str] = None) -> str:
        """Post a tweet via X API v2. Returns tweet ID."""
        from x_client import post_tweet as _x_post
        tweet_id = await _x_post(text, reply_to=reply_to)
        if tweet_id:
            return tweet_id
        raise Exception("X API post failed — check X_CONSUMER_KEY / X_ACCESS_TOKEN env vars")

    async def post_thread(self, tweets: List[str]) -> List[str]:
        """Post a thread by chaining replies."""
        ids = []
        reply_to = None
        for text in tweets:
            tweet_id = await self.post_tweet(text, reply_to=reply_to)
            ids.append(tweet_id)
            reply_to = tweet_id
        return ids

    async def like_tweet(self, tweet_id: str) -> bool:
        """Like a tweet via X API v2."""
        from x_client import like_tweet as _x_like
        return await _x_like(tweet_id)

    async def retweet(self, tweet_id: str) -> bool:
        """Retweet via X API v2."""
        from x_client import retweet as _x_retweet
        return await _x_retweet(tweet_id)

    async def follow_user(self, username: str) -> bool:
        logger.info(f"follow_user({username}) — not implemented")
        return False

    async def search_tweets(self, query: str, limit: int = 10, latest: bool = False) -> List[dict]:
        """Search recent tweets via X API v2 (requires Basic tier)."""
        try:
            from x_client import search_alpha
            results = await search_alpha(query, max_results=max(10, min(100, limit)))
            return results or []
        except Exception as e:
            logger.warning(f"search_tweets error: {e}")
            return []

    async def get_home_timeline(self, limit: int = 20) -> List[dict]:
        return []

    async def check_connection(self) -> dict:
        """Verify X API credentials."""
        try:
            from x_client import _get_me_id
            me_id = await _get_me_id()
            if me_id:
                return {"ok": True, "user_id": me_id}
            return {"ok": False, "reason": "credentials missing or invalid"}
        except Exception as e:
            return {"ok": False, "reason": str(e)}
