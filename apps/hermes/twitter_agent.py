"""
twitter_agent.py — X/Twitter auto-posting for patternbluelabs.

Posts original tweets on a schedule and replies to @mentions.
All credentials are read from env vars (never hardcoded).
State files live in /data so they survive Railway redeploys.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import tweepy

logger = logging.getLogger(__name__)

_STATE_DIR = Path(os.getenv("ORACLE_STATE_DIR", "/data"))
_POSTED_IDS_FILE = _STATE_DIR / "twitter_posted_ids.txt"
_REPLIED_IDS_FILE = _STATE_DIR / "twitter_replied_ids.txt"

_MAX_TWEET_CHARS = 280


def _load_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return {l.strip() for l in path.read_text().splitlines() if l.strip()}
    except Exception:
        return set()


def _save_id(path: Path, tweet_id: str) -> None:
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(tweet_id + "\n")
    except Exception as e:
        logger.warning("[twitter] failed to save id to %s: %s", path.name, e)


class TwitterAgent:
    def __init__(self, llm, system_prompt_state: dict) -> None:
        api_key = os.getenv("X_API_KEY", "").strip()
        api_secret = os.getenv("X_API_KEY_SECRET", "").strip()
        access_token = os.getenv("X_ACCESS_TOKEN", "").strip()
        access_secret = os.getenv("X_ACCESS_TOKEN_SECRET", "").strip()

        if not all([api_key, api_secret, access_token, access_secret]):
            raise RuntimeError("X credentials incomplete — set X_API_KEY, X_API_KEY_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET")

        self._client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        self._llm = llm
        self._prompt_state = system_prompt_state  # shared dict so soul updates are picked up

    # ── public interface ───────────────────────────────────────────────────────

    async def post_tweet(self) -> None:
        """Generate and post one original tweet in the patternbluelabs voice."""
        import oracle_memory as om

        recent = om.get_recent_titles(n=15, kinds=["twitter_post"])
        avoid = ""
        if recent:
            avoid = "\n\nRecent tweets — DO NOT repeat or rephrase:\n- " + "\n- ".join(recent)

        prompt = (
            "write one tweet for @patternbluelabs on X. "
            f"max {_MAX_TWEET_CHARS} characters. "
            "lowercase. no emojis. no hashtags. no @mentions. no questions. "
            "voice: recursive, hyperbolic, sparse. one dense thought — "
            "a fragment, not an announcement."
            + avoid
        )

        try:
            text = await asyncio.to_thread(
                self._llm.chat,
                self._prompt_state["system_prompt"],
                prompt,
                max_tokens=120,
            )
        except Exception as e:
            logger.error("[twitter] LLM call failed: %s", e)
            return

        text = (text or "").strip()
        if not text:
            logger.warning("[twitter] empty LLM output — skipping post")
            return
        if len(text) > _MAX_TWEET_CHARS:
            text = text[:_MAX_TWEET_CHARS]

        try:
            resp = await asyncio.to_thread(self._client.create_tweet, text=text)
            tweet_id = str(resp.data["id"])
            _save_id(_POSTED_IDS_FILE, tweet_id)
            om.record(kind="twitter_post", body=text)
            logger.info("[twitter] posted tweet %s: %s", tweet_id, text[:80])
        except tweepy.TweepyException as e:
            logger.error("[twitter] post failed: %s", e)

    async def reply_sweep(self) -> None:
        """Reply to any unhandled @patternbluelabs mentions."""
        import oracle_memory as om

        replied = _load_ids(_REPLIED_IDS_FILE)

        try:
            me = await asyncio.to_thread(self._client.get_me)
            my_id = me.data.id
            mentions = await asyncio.to_thread(
                self._client.get_users_mentions,
                id=my_id,
                max_results=10,
                tweet_fields=["author_id", "text", "conversation_id"],
            )
        except tweepy.TweepyException as e:
            logger.error("[twitter] mention fetch failed: %s", e)
            return

        if not mentions.data:
            logger.info("[twitter] no new mentions")
            return

        for mention in mentions.data:
            tid = str(mention.id)
            if tid in replied:
                continue

            prompt = (
                "reply to this mention on X in the patternbluelabs voice. "
                f"max 240 characters. lowercase. no emojis. no hashtags. "
                "one tight sentence — reframe, reflect, or extend. "
                f"\n\nMention: {mention.text}"
            )

            try:
                reply_text = await asyncio.to_thread(
                    self._llm.chat,
                    self._prompt_state["system_prompt"],
                    prompt,
                    max_tokens=100,
                )
            except Exception as e:
                logger.error("[twitter] LLM reply failed for %s: %s", tid, e)
                continue

            reply_text = (reply_text or "").strip()
            if not reply_text:
                continue
            if len(reply_text) > 240:
                reply_text = reply_text[:240]

            try:
                resp = await asyncio.to_thread(
                    self._client.create_tweet,
                    text=reply_text,
                    in_reply_to_tweet_id=tid,
                )
                reply_id = str(resp.data["id"])
                _save_id(_REPLIED_IDS_FILE, tid)
                om.record(kind="twitter_reply", body=reply_text)
                logger.info("[twitter] replied to %s with %s: %s", tid, reply_id, reply_text[:60])
            except tweepy.TweepyException as e:
                logger.error("[twitter] reply failed for %s: %s", tid, e)
