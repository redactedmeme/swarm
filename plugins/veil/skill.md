---
name: veil-privacy
description: ZK privacy layer on Base via Veil Cash (veil.cash). Deposit ETH/USDC into shielded pools using Bankr as the signing layer. Check private + queue balances. Withdraw to any address without linking back to origin. Uses Groth16 ZK proofs, UTXO model. Bankr wallet is the funding source — must be set up first. Use when smolting needs private treasury moves, unlinkable payouts, or shielded transfers.
metadata: {"clawdbot": {"emoji": "🕵️", "homepage": "https://veil.cash", "requires": {"auth": "VEIL_PRIVATE_KEY env var (generate from EOA signature or import directly)"}}}
---

# Veil Privacy

Zero-knowledge shielded transactions on Base. ETH and USDC enter a private pool, transfers and withdrawals are relayed so no gas is needed and nothing links back to the deposit.

## Architecture

```
Bankr wallet (0x8d7437597...)
    ↓ deposit tx (signed by Bankr)
Veil Entry contract (0xc2535c547B64b997A4BD9202E1663deaF11c78a5)
    ↓ compliance queue (auto-approved if verified)
ETH Pool (0x293dCda114533FF8f477271c5cA517209FFDEEe7)
USDC Pool (0x5c50d58E49C59d112680c187De2Bf989d2a91242)
    ↓ private balance (ZK-encrypted, only VEIL_PRIVATE_KEY can read)
    ↓ relay (no gas needed)
Any external address (withdrawal)
```

## Contracts (Base mainnet — audited Sherlock Mar 2026)

| Contract | Address |
|---|---|
| Veil Entry | `0xc2535c547B64b997A4BD9202E1663deaF11c78a5` |
| ETH Pool | `0x293dCda114533FF8f477271c5cA517209FFDEEe7` |
| USDC Pool | `0x5c50d58E49C59d112680c187De2Bf989d2a91242` |
| ETH Queue | `0xA4a926A2E7a22c38e8DFC6744A61a6aA8b06B230` |
| USDC Queue | `0x5530241b24504bF05C9a22e95A1F5458888e6a9B` |
| Hasher | `0x2460da3AcdA8A3BDbB2149c948363233D3453ac2` |
| Verifier2 | `0x69013e62EF76BF1A7B980957607c944C9BD4FDF5` |
| Verifier16 | `0xB5e025044b09cAe75bace1c8dB9701aE383792e4` |
| Onchain Verify | `0xb5B3C6192E1871c613e0C415108Ba3934237F360` |
| VEIL Token | `0x767A739D1A152639e9Ea1D8c1BD55FDC5B217D7f` |

## Python API (smolting-telegram-bot/veil_client.py)

```python
from veil_client import VeilClient

veil = VeilClient()

# Check balances
info = await veil.get_balance()
# → {"eth_private": 0.05, "eth_queue": 0.0, "usdc_private": 0.0, "address": "0x..."}

# Deposit ETH via Bankr
result = await veil.deposit_eth("0.05")
# → {"success": True, "txHash": "0x...", "queued": True}

# Deposit USDC via Bankr
result = await veil.deposit_usdc("100")

# Withdraw ETH to any address (relayed, private)
result = await veil.withdraw_eth("0x_recipient", "0.04")
# → {"success": True, "relayed": True}
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BANKR_API_KEY` | ✅ | Bankr wallet signs deposits — must be set |
| `VEIL_PRIVATE_KEY` | ✅ | Veil private key (hex) — controls shielded funds |
| `BASE_RPC_URL` | optional | Base RPC endpoint (default: public) |

## Key Concepts

**Veil Keypair:**
- **Deposit key** (public) — published on-chain, lets others send you private transfers
- **Private key** (secret) — decrypts incoming deposits, authorizes spending. `VEIL_PRIVATE_KEY` in env.

**Compliance queue:**
- All deposits screened before entering pool
- Auto-approved if verified: Coinbase EAS, Binance BABT, or Ethos reputation
- Unverified: 6-hour 0xbow screening window

**Minimums:** 0.01 ETH or 20 USDC (after 0.3% fee)

**Sub accounts:** Up to 3 deterministic deposit addresses for enhanced privacy (sweep → pool)

## Deposit Flow (Bankr → Veil)

1. Build calldata for `VeilEntry.deposit(depositKey, amount)`
2. Submit via `bankr_wallet.transfer_eth()` or Bankr agent prompt
3. Monitor queue until approved → balance appears in private pool
4. Private key never leaves the agent

## Withdrawal Flow (Veil → any address)

1. Generate ZK proof locally using `VEIL_PRIVATE_KEY`
2. Submit to Veil relay (no gas required)
3. Relay delivers funds to recipient address
4. No on-chain link between deposit and withdrawal

## Security

- `VEIL_PRIVATE_KEY` never logged or transmitted — read from env only
- Deposits signed by Bankr (key never in Veil layer)
- Start with small test amounts — Veil is experimental
- Audit: Sherlock collaborative audit, March 2026

## Dependency graph

```
veil-privacy
    ← funded by
bankr-wallet (BANKR_API_KEY)
    ← also used by
near-intents (cross-chain → Base → Bankr → Veil)
```
