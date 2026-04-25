# Automation

Set up limit orders, stop-loss, DCA, TWAP, and scheduled commands.

## Order Types

### Limit Orders
```
"Set a limit order to buy ETH at $3,000"
"Limit order: sell BNKR when it hits $0.02"
"Buy 1 SOL if price drops to $100"
```

### Stop Loss
```
"Set stop loss for my ETH at $2,500"
"Stop loss: sell 50% of BNKR if it drops 20%"
```

### DCA (Dollar Cost Averaging)
```
"DCA $100 into ETH every week"
"Set up daily $50 Bitcoin purchases"
"Buy $25 of SOL every Monday"
```

Intervals: hourly, daily, weekly, monthly.

### TWAP (Time-Weighted Average Price)
```
"TWAP: buy $1000 of ETH over 24 hours"
"Spread my sell order over 4 hours"
```

### Scheduled Commands
```
"Every morning at 8am, check my portfolio"
"Daily at 9am, check ETH price"
```

## Managing Automations

```
"Show my automations"
"Cancel my ETH limit order"
"Stop my DCA into Bitcoin"
```

To modify: cancel and recreate with new parameters.

## Chain Support

| Feature | EVM (Base/Polygon/ETH) | Solana |
|---------|------------------------|--------|
| Limit orders | ✅ | ✅ (Jupiter Trigger) |
| Stop loss | ✅ | ✅ |
| DCA | ✅ | ✅ |
| TWAP | ✅ | ⚠️ limited |
| Scheduled commands | ✅ | ✅ |

## Cost Considerations

- Gas fee per execution — very low on Base/Polygon
- Daily DCA = 365 transactions/year; weekly may be more efficient
- TWAP: total gas = intervals × gas per tx

## Combined Strategies

- DCA + stop loss = Protected accumulation
- Limit buy + limit sell = Range trading
- TWAP + stop loss = Large position exit
