# Transfers

Transfer tokens to addresses, ENS names, or social handles.

## CLI Command

```bash
# Transfer with token symbol resolution
bankr wallet transfer --to <recipient> --token <symbol> --amount <amount>
bankr wallet transfer --to <recipient> --token <symbol> --amount <amount> --chain <chain>

# Examples
bankr wallet transfer --to vitalik.eth --token USDC --amount 50 --chain base
bankr wallet transfer --to 0x1234... --token ETH --amount 0.1
bankr wallet transfer --to @friend --token USDC --amount 20
```

## REST API

```bash
curl -X POST "https://api.bankr.bot/wallet/transfer" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"to": "vitalik.eth", "token": "USDC", "amount": "50", "chain": "base"}'
```

The `/wallet/transfer` endpoint is a write endpoint — requires `walletApiEnabled`, `readOnly: false`, and is subject to `allowedRecipients` enforcement and IP allowlist.

## Supported Chains

- **EVM**: Base, Polygon, Ethereum, Unichain, World Chain, Arbitrum, BNB Chain
  - Native tokens: ETH, POL, BNB
  - ERC20 tokens: USDC, USDT, WETH, etc.
- **Solana**: SOL and SPL tokens

## Recipient Formats

| Format | Example | Description |
|--------|---------|-------------|
| Address | `0x1234...abcd` | Direct EVM wallet address |
| Address | `9x...abc` | Direct Solana wallet address |
| ENS | `vitalik.eth` | Ethereum Name Service |
| Twitter | `@elonmusk` | Twitter/X username |
| Farcaster | `@dwr.eth` | Farcaster username |
| Telegram | `@username` | Telegram handle |

Social handles are resolved to linked wallet addresses before sending.

## Amount Formats

| Format | Example |
|--------|---------|
| USD | `$50` |
| Percentage | `50%` |
| Exact | `0.1 ETH` |

## Security Notes

- **Verify recipient** before confirming — blockchain transactions cannot be undone
- **Test first** — send small amount to new recipients
- Social handle resolution shows the resolved address for verification
