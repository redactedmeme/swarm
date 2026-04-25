# bankr-wallet

Headless cross-chain wallet for smolting and the REDACTED swarm, powered by [Bankr](https://bankr.bot).

## Why Bankr

- **No interactive auth** — API key only, works in headless Railway deployments
- **Base-native** — first-class EVM support with sponsored gas
- **Multi-chain** — Base, Solana, Polygon, Unichain, Arbitrum, World Chain, BNB
- **Veil-ready** — Bankr is the funding source for ZK-shielded Veil flows

## Files

| File | Purpose |
|---|---|
| `smolting-telegram-bot/bankr_wallet.py` | Python async client (aiohttp) |
| `plugins/bankr-wallet/skill.md` | Full skill definition + API reference |
| `plugins/bankr-wallet/.env.example` | Environment variable template |

## Quick start

### 1. Get a Bankr API key
Create a **dedicated agent account** (not your personal account) at [bankr.bot](https://bankr.bot), then generate an API key at bankr.bot/api.

### 2. Set the env var in Railway
```
BANKR_API_KEY=your_key_here
```

### 3. Test connectivity
```bash
curl https://api.bankr.bot/wallet/me \
  -H "X-API-Key: $BANKR_API_KEY"
```

### 4. Use in smolting
```python
from bankr_wallet import get_wallet_summary, transfer_usdc, agent_run

summary = await get_wallet_summary()
# {"ready": True, "address": "0x...", "eth_balance": ..., "usdc_balance": ..., "total_usd": ...}
```

## What's next

Once `BANKR_API_KEY` is set and the wallet is funded:
1. **Veil integration** — use Bankr as the deposit source for ZK-shielded `plugins/veil/` flows
2. **LLM tool calling** — expose `bankr_transfer` and `bankr_swap` as tools in `llm_tools.py`
3. **Autonomous payments** — smolting pays for mesh services via x402 + Bankr
