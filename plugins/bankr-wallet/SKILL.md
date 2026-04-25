# Bankr: AI-Powered Crypto Trading Agent

> Official skill definition from https://github.com/BankrBot/skills/tree/main/bankr

**Bankr** is a natural language crypto trading platform offering AI-driven portfolio management, DeFi operations, and wallet functionality across multiple blockchains.

## Key Features

**Trading & Portfolio**
- Token swaps, limit orders, and stop-loss automation
- Multi-chain portfolio tracking with real-time valuations
- Cross-chain bridging and dollar-cost averaging (DCA)

**Supported Chains**
Base, Ethereum, Polygon, Solana, and Unichain with varying gas costs and use cases.

**Advanced Capabilities**
- Leverage trading via Hyperliquid (up to 50x) and Avantis
- Polymarket prediction market betting
- NFT discovery and purchases
- Token deployment (ERC20 on Base, SPL on Solana)
- x402 paid API endpoint integration

## Getting Started

**Two Integration Options:**

1. **CLI** (recommended) — Install `@bankr/cli` for terminal access
2. **REST API** — Call `https://api.bankr.bot` directly

Both require an API key (format: `bk_...`).

### Quick Setup

```bash
# Step 1: Request verification code
bankr login email your@email.com

# Step 2: Complete setup with your OTP
bankr login email your@email.com --code 123456 --accept-terms \
  --key-name "My Agent" --agent-api --read-write
```

## Basic Commands

```bash
bankr wallet portfolio              # Check balances
bankr agent prompt "Buy $50 ETH"    # Natural language trading
bankr tokens search PEPE             # Find tokens
```

## Security Best Practices

- Store API keys in environment variables only
- Use dedicated agent wallets with limited funds
- Enable IP whitelisting for server-side deployments
- Test with small amounts on low-cost chains (Base/Polygon) first
- Add `~/.bankr/` to `.gitignore`

## LLM Gateway

Bankr provides unified API access to Claude, Gemini, GPT, and other models at `https://llm.bankr.bot`. Credits operate separately from trading balances—new accounts start with $0 and require top-ups before making LLM calls.

**Resources**: [bankr.bot](https://bankr.bot) | [Documentation](https://docs.bankr.bot) | [@bankr_bot](https://twitter.com/bankr_bot)

## Reference Docs

See `references/` for detailed guides on each capability:

| File | Topic |
|---|---|
| `agent-profiles.md` | Public agent showcase pages |
| `api-workflow.md` | Submit-poll-complete async pattern |
| `arbitrary-transaction.md` | Raw EVM transaction submission |
| `automation.md` | Limit orders, stop-loss, DCA, TWAP |
| `error-handling.md` | Troubleshooting and error codes |
| `hyperliquid.md` | Perpetual futures on Hyperliquid |
| `leverage-trading.md` | Leverage up to 50x/100x |
| `llm-gateway.md` | Multi-provider LLM access |
| `market-research.md` | Price data, TA, sentiment |
| `nft-operations.md` | NFT browsing and purchasing |
| `polymarket.md` | Prediction market betting |
| `portfolio.md` | Balance and portfolio queries |
| `safety.md` | API key management, IP allowlists |
| `sign-submit-api.md` | Low-level sign/submit endpoints |
| `token-deployment.md` | ERC20 / SPL token launches |
| `token-trading.md` | Swaps and chain selection |
| `transfers.md` | Send to address/ENS/social handle |
| `x402-cloud.md` | Paid API endpoint deployment |
