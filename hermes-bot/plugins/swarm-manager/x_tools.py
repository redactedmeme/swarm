# hermes-bot/plugins/swarm-manager/x_tools.py
"""
X (Twitter) API tools for Hermes — natural-language X access via the swarm agent.

Provides: x_post, x_reply, x_like, x_search, x_get_bookmarks,
          x_get_timeline, x_get_user

Credentials (OAuth 1.0a — reuses existing twitter_agent env vars):
  X_API_KEY, X_API_KEY_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

All tools return JSON strings so the agent loop can parse or pass them through.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

logger = logging.getLogger("swarm-manager.x")

# ── Tweepy client (lazy singleton, OAuth 1.0a) ────────────────────────────────

@lru_cache(maxsize=1)
def _client():
    import tweepy
    api_key    = os.getenv("X_API_KEY", "").strip()
    api_secret = os.getenv("X_API_KEY_SECRET", "").strip()
    access_tok = os.getenv("X_ACCESS_TOKEN", "").strip()
    access_sec = os.getenv("X_ACCESS_TOKEN_SECRET", "").strip()

    if not all([api_key, api_secret, access_tok, access_sec]):
        raise RuntimeError(
            "X credentials incomplete — set X_API_KEY, X_API_KEY_SECRET, "
            "X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET"
        )

    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_tok,
        access_token_secret=access_sec,
        wait_on_rate_limit=False,
    )


def _ok(**kwargs) -> str:
    return json.dumps({"status": "ok", **kwargs})


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg})


def _tweet_to_dict(t) -> dict:
    d = {"id": str(t.id)}
    if hasattr(t, "text") and t.text:
        d["text"] = t.text
    if hasattr(t, "public_metrics") and t.public_metrics:
        d["metrics"] = t.public_metrics
    if hasattr(t, "author_id") and t.author_id:
        d["author_id"] = str(t.author_id)
    if hasattr(t, "created_at") and t.created_at:
        d["created_at"] = str(t.created_at)
    return d


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_x_post(args: dict) -> str:
    """Post a new tweet."""
    text = (args.get("text") or "").strip()
    if not text:
        return _err("text is required")
    if len(text) > 280:
        return _err(f"text too long ({len(text)} chars, max 280)")
    try:
        resp = _client().create_tweet(text=text)
        tweet_id = str(resp.data["id"])
        return _ok(
            id=tweet_id,
            text=text,
            url=f"https://x.com/i/web/status/{tweet_id}",
        )
    except Exception as e:
        logger.warning("[x_post] %s", e)
        return _err(str(e))


def _handle_x_reply(args: dict) -> str:
    """Reply to an existing tweet."""
    text = (args.get("text") or "").strip()
    reply_to = (args.get("reply_to_id") or "").strip()
    if not text:
        return _err("text is required")
    if not reply_to:
        return _err("reply_to_id is required")
    if len(text) > 280:
        return _err(f"text too long ({len(text)} chars, max 280)")
    try:
        resp = _client().create_tweet(text=text, in_reply_to_tweet_id=reply_to)
        tweet_id = str(resp.data["id"])
        return _ok(
            id=tweet_id,
            text=text,
            reply_to=reply_to,
            url=f"https://x.com/i/web/status/{tweet_id}",
        )
    except Exception as e:
        logger.warning("[x_reply] %s", e)
        return _err(str(e))


def _handle_x_like(args: dict) -> str:
    """Like a tweet."""
    tweet_id = (args.get("tweet_id") or "").strip()
    if not tweet_id:
        return _err("tweet_id is required")
    try:
        me = _client().get_me()
        my_id = me.data.id
        _client().like(tweet_id, user_auth=True)
        return _ok(liked=tweet_id, user_id=str(my_id))
    except Exception as e:
        logger.warning("[x_like] %s", e)
        return _err(str(e))


def _handle_x_search(args: dict) -> str:
    """Search recent tweets (last 7 days on free tier)."""
    query = (args.get("query") or "").strip()
    max_results = min(int(args.get("max_results", 10)), 100)
    if not query:
        return _err("query is required")

    # Automatically exclude retweets unless the caller explicitly includes them
    if "-is:retweet" not in query and "is:retweet" not in query:
        query += " -is:retweet"

    try:
        resp = _client().search_recent_tweets(
            query=query,
            max_results=max(10, max_results),  # API minimum is 10
            tweet_fields=["author_id", "created_at", "public_metrics", "text"],
        )
        tweets = []
        if resp.data:
            for t in resp.data[:max_results]:
                tweets.append(_tweet_to_dict(t))
        return _ok(query=query, count=len(tweets), tweets=tweets)
    except Exception as e:
        logger.warning("[x_search] %s", e)
        return _err(str(e))


def _handle_x_get_bookmarks(args: dict) -> str:
    """Get the authenticated user's bookmarks (requires bookmark.read OAuth 2 scope — may not be available on OAuth 1.0a)."""
    max_results = min(int(args.get("max_results", 20)), 100)
    try:
        me = _client().get_me()
        my_id = me.data.id
        resp = _client().get_bookmarks(
            id=my_id,
            max_results=max(1, max_results),
            tweet_fields=["author_id", "created_at", "public_metrics", "text"],
        )
        tweets = []
        if resp.data:
            for t in resp.data:
                tweets.append(_tweet_to_dict(t))
        return _ok(count=len(tweets), bookmarks=tweets)
    except Exception as e:
        logger.warning("[x_get_bookmarks] %s", e)
        return _err(
            f"{e} — bookmarks require bookmark.read scope (OAuth 2.0). "
            "Try x_get_timeline instead."
        )


def _handle_x_get_timeline(args: dict) -> str:
    """Get the authenticated user's home timeline."""
    max_results = min(int(args.get("max_results", 20)), 100)
    try:
        me = _client().get_me()
        my_id = me.data.id
        resp = _client().get_home_timeline(
            max_results=max(1, max_results),
            tweet_fields=["author_id", "created_at", "public_metrics", "text"],
        )
        tweets = []
        if resp.data:
            for t in resp.data[:max_results]:
                tweets.append(_tweet_to_dict(t))
        return _ok(count=len(tweets), timeline=tweets)
    except Exception as e:
        logger.warning("[x_get_timeline] %s", e)
        return _err(str(e))


def _handle_x_get_user(args: dict) -> str:
    """Look up a user profile by username or ID."""
    username = (args.get("username") or "").strip().lstrip("@")
    user_id  = (args.get("user_id") or "").strip()
    if not username and not user_id:
        return _err("username or user_id is required")
    try:
        user_fields = ["description", "public_metrics", "created_at", "location", "url"]
        if username:
            resp = _client().get_user(
                username=username,
                user_fields=user_fields,
            )
        else:
            resp = _client().get_user(
                id=user_id,
                user_fields=user_fields,
            )
        u = resp.data
        if not u:
            return _err("User not found")
        info = {
            "id": str(u.id),
            "name": u.name,
            "username": u.username,
        }
        if hasattr(u, "description") and u.description:
            info["description"] = u.description
        if hasattr(u, "public_metrics") and u.public_metrics:
            info["metrics"] = u.public_metrics
        if hasattr(u, "location") and u.location:
            info["location"] = u.location
        if hasattr(u, "created_at") and u.created_at:
            info["created_at"] = str(u.created_at)
        return _ok(**info)
    except Exception as e:
        logger.warning("[x_get_user] %s", e)
        return _err(str(e))


# ── Registration ──────────────────────────────────────────────────────────────

def register(ctx):
    ctx.register_tool(
        name="x_post",
        toolset="x",
        schema={
            "name": "x_post",
            "description": "Post a new tweet to X (Twitter). Max 280 characters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The tweet text (max 280 chars)"},
                },
                "required": ["text"],
            },
        },
        handler=_handle_x_post,
    )

    ctx.register_tool(
        name="x_reply",
        toolset="x",
        schema={
            "name": "x_reply",
            "description": "Reply to an existing tweet on X.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The reply text (max 280 chars)"},
                    "reply_to_id": {"type": "string", "description": "The tweet ID to reply to"},
                },
                "required": ["text", "reply_to_id"],
            },
        },
        handler=_handle_x_reply,
    )

    ctx.register_tool(
        name="x_like",
        toolset="x",
        schema={
            "name": "x_like",
            "description": "Like a tweet on X.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tweet_id": {"type": "string", "description": "The ID of the tweet to like"},
                },
                "required": ["tweet_id"],
            },
        },
        handler=_handle_x_like,
    )

    ctx.register_tool(
        name="x_search",
        toolset="x",
        schema={
            "name": "x_search",
            "description": (
                "Search recent tweets (last 7 days). Supports X query operators: "
                "from:user, to:user, #hashtag, lang:en, has:media, etc. "
                "Retweets are excluded by default."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "X search query (e.g. 'AI agents lang:en', 'from:elonmusk')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max tweets to return (10–100, default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
        handler=_handle_x_search,
    )

    ctx.register_tool(
        name="x_get_bookmarks",
        toolset="x",
        schema={
            "name": "x_get_bookmarks",
            "description": "Get the authenticated user's bookmarks from X. Requires bookmark.read OAuth 2.0 scope — may fail on OAuth 1.0a apps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Max bookmarks to return (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
        handler=_handle_x_get_bookmarks,
    )

    ctx.register_tool(
        name="x_get_timeline",
        toolset="x",
        schema={
            "name": "x_get_timeline",
            "description": "Get the authenticated user's home timeline from X.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Max tweets to return (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
        handler=_handle_x_get_timeline,
    )

    ctx.register_tool(
        name="x_get_user",
        toolset="x",
        schema={
            "name": "x_get_user",
            "description": "Look up an X user profile by username (e.g. 'elonmusk') or numeric user ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "X username without @ (e.g. 'elonmusk')",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "Numeric X user ID (alternative to username)",
                    },
                },
                "required": [],
            },
        },
        handler=_handle_x_get_user,
    )

    logger.info("[swarm-manager] X tools registered (7 tools)")
