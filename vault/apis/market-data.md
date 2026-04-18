# Market Data — smolting /alpha

**File:** `smolting-telegram-bot/market_data.py`

---

## Sources

| Function | Source | Auth | Cache |
|----------|--------|------|-------|
| `fetch_dexscreener(token)` | DexScreener v1 | None | None |
| `fetch_birdeye_overview(token)` | Birdeye | `BIRDEYE_API_KEY` | 5 min |
| `fetch_birdeye_ohlcv(token)` | Birdeye | `BIRDEYE_API_KEY` | None |
| `fetch_birdeye_trending()` | Birdeye | `BIRDEYE_API_KEY` | None |
| `fetch_coingecko_sol()` | CoinGecko | None | None |
| `fetch_coingecko_global()` | CoinGecko | None | None |
| `fetch_jupiter_price(token)` | Jupiter Price v2 | None | None |
| `fetch_x_intelligence(query)` | xAI Grok-3-mini + x_search | `XAI_API_KEY` | None |

All fetched via `get_alpha_context()` → `asyncio.gather(..., return_exceptions=True)`.

---

## Token Constants

```python
REDACTED_V2 = os.getenv("REDACTED_TOKEN", "9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump")
REDACTED_V1 = "9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM"
SOL_MINT    = "So11111111111111111111111111111111111111112"
```

---

## Birdeye Notes

- 429 on rate limit → returns cached data, logs warning
- Cache key: `"overview:{token_address}"`, TTL: 300s
- Handles multiple field name variants (`holder`, `holders`, `holderCount`, `uniqueWallets`)

---

## xAI x_search Notes

- Model: `grok-3-mini` via `/v1/responses` endpoint (Responses API, not Chat)
- Tool: `{"type": "x_search"}`
- 403 = no billing credits at `console.x.ai` → returns `None` silently
- Used for live CT/X sentiment in `/alpha` context

---

## Usage

```python
from market_data import get_alpha_context, format_alpha_context

ctx = await get_alpha_context()
prompt_str = format_alpha_context(ctx)
# feed prompt_str to LLM for /alpha response
```
