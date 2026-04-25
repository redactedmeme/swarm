# Portfolio

Check token balances and holdings across multiple blockchains.

## CLI

```bash
bankr wallet portfolio                        # All chains
bankr wallet portfolio --chain base,solana    # Filter by chain
bankr wallet portfolio --pnl                  # Include profit/loss
bankr wallet portfolio --nfts                 # Include NFTs
```

## REST API

```bash
GET https://api.bankr.bot/wallet/portfolio
  ?chains=base,solana
  &include=pnl,nfts
  &showLowValueTokens=true
```

Supported chains: `base`, `polygon`, `mainnet`, `unichain`, `worldchain`, `arbitrum`, `bnb`, `solana`

## Notes

- Read-only — requires only a valid API key
- Balances under $1 hidden by default in CLI; use `?showLowValueTokens=true` to show
- PnL and NFT data use progressive loading — only fetched when requested
- `/agent/balances` is deprecated; use `/wallet/portfolio`

## Response Shape

Returns wallet balances across chains with:
- EVM and Solana addresses
- Native and token balances with USD values
- Optional PnL (realized, unrealized, total)
- Optional NFT holdings
