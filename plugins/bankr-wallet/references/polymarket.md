# Polymarket

Prediction market betting on Polygon using USDC.e.

## How It Works

- Purchase "Yes" or "No" shares
- Prices reflect probabilities (e.g. $0.60 = 60% chance)
- Winning shares pay out $1.00 each
- Profit = redemption value − purchase price

Auto-bridging available for USDC from other chains.

## Market Categories

Politics, sports, crypto, culture, business, world events.

## Market Phases

`Active` → `Closed` → `Resolved`

Shares can be sold before resolution.

## Prompt Examples

```
"Show me trending Polymarket markets"
"What are the odds on the next Fed rate decision?"
"Bet $20 on Yes for [market]"
"Show my open Polymarket positions"
"Redeem my winning shares"
```

## REST API

```bash
GET https://api.bankr.bot/polymarket/positions
  -H "X-API-Key: $BANKR_API_KEY"
```

## Best Practices

- Start with small amounts
- Diversify across multiple markets
- Understand resolution criteria before betting
- Never bet more than you can afford to lose
- Check liquidity before placing large bets
