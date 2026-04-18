# xREDACTED — X/Twitter Client

**Previously:** ClawnX (renamed 2026-04-17)  
**Files:**
- `smolting-telegram-bot/xredacted.py` — `XRedacted` class (thin wrapper)
- `smolting-telegram-bot/x_client.py` — direct OAuth 1.0a implementation (tweepy v2)
- `smolting-telegram-bot/clawnx_integration.py` — deprecation shim → imports `XRedacted as ClawnXClient`

---

## Credentials (Railway env vars)

| Var | Description |
|-----|-------------|
| `X_CONSUMER_KEY` | OAuth 1.0a consumer key |
| `X_CONSUMER_SECRET` | OAuth 1.0a consumer secret |
| `X_ACCESS_TOKEN` | Access token |
| `X_ACCESS_TOKEN_SECRET` | Access token secret |

If any credential is missing, `XRedacted._ready = False` and all posting is silently disabled.

---

## API

```python
from xredacted import XRedacted
x = XRedacted()

# Post a single tweet (truncated to 280 chars)
tweet_id = await x.post_tweet("text", reply_to=None)

# Post a thread (chains replies)
ids = await x.post_thread(["tweet 1", "tweet 2", "tweet 3"])

# Engagement
await x.like_tweet(tweet_id)
await x.retweet(tweet_id)

# Search (requires X API Basic tier — $100/mo)
tweets = await x.search_tweets("query", limit=10)

# Health check
status = await x.check_connection()  # {"ok": True, "user_id": "..."}
```

---

## Notes

- `wait_on_rate_limit=True` — tweepy handles backoff automatically
- Search returns `None` on free tier (403 Forbidden) — not an error
- `_get_me_id()` cached after first call
- For RedactedDegen: copy `x_client.py` directly, skip the `XRedacted` wrapper class
