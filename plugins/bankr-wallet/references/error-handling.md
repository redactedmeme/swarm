# Error Handling

## HTTP Status Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| 400 | Bad request | Check request format and required fields |
| 401 | Invalid API key | Verify `BANKR_API_KEY` is set correctly |
| 402 | Payment required | Add LLM credits at bankr.bot (for LLM Gateway) |
| 403 | Forbidden | `walletApiEnabled` not set, or read-only key |
| 429 | Rate limited | Back off and retry; check daily message limit |

## Common Issues

**Authentication (401):**
```bash
# Install CLI
bun install -g @bankr/cli
# Login or set key directly
bankr login
export BANKR_API_KEY=bk_...
```

**Transaction failures:**
- Insufficient balance → reduce amount or fund wallet
- Token not found → verify symbol and chain
- Slippage exceeded → retry or increase tolerance
- Network congestion → retry after delay

**Write operations returning 403:**
- Key needs `walletApiEnabled` — request from Bankr
- Key may be `readOnly: true`

## Debugging Checklist

1. Verify internet connectivity
2. Test API reachability: `curl https://api.bankr.bot/wallet/me -H "X-API-Key: $BANKR_API_KEY"`
3. Confirm wallet is funded (including gas buffer)
4. Check token exists on specified chain
5. Verify no typos in token symbol or chain name

## Prevention

- Always keep a gas buffer of native tokens
- Test transactions on small amounts first
- Specify chain explicitly for lesser-known tokens
- Never use 100% of balance — leave room for gas

## Support

- Twitter: [@bankr_bot](https://twitter.com/bankr_bot)
- Telegram: [@bankr_ai_bot](https://t.me/bankr_ai_bot)
