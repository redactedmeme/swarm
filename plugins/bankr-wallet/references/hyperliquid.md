# Hyperliquid

Trade perpetual futures and spot on Hyperliquid's L1 DEX via Bankr.

## Key Details

- Collateral: USDC (5 USDC minimum deposit)
- Leverage: up to 50x on perps
- Funding rates charge every 8 hours

## Operations

**Open position:**
```
"Open a 5x long ETH position with $100"
"Short BTC with 10x leverage, $50 collateral"
```

**Spot trading:**
```
"Buy 10 HL tokens"
"Sell my HYPE spot position"
```

**Order management:**
```
"Set take profit at $4000 for my ETH long"
"Set stop loss at $2800"
"Close my ETH position"
```

**Bridge:**
```
"Deposit 100 USDC to Hyperliquid from Base"
"Withdraw 50 USDC from Hyperliquid"
```

**Account:**
```
"Show my Hyperliquid balance"
"What are my open positions?"
```

## TP/SL Notes

- New positions: supports price, ROE%, or delta formats
- Existing positions: absolute prices only

## Safety

Leverage amplifies both gains and losses — total collateral loss is possible. Always use stop-loss orders.
