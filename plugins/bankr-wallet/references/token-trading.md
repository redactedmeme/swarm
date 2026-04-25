# Token Trading

Execute token swaps across Base, Polygon, Ethereum, Unichain, and Solana.

## Amount Formats

| Format | Example |
|--------|---------|
| USD | `$50` |
| Percentage | `50%` |
| Exact | `0.1 ETH` |

## Chain Selection

If not specified, the system picks the optimal chain. Base is preferred for most operations due to low fees.

## Prompt Examples

**Same-chain:**
- "Swap 0.1 ETH for USDC on Base"
- "Buy $50 of ETH"
- "Sell 50% of my ETH holdings"

**Cross-chain:**
- "Bridge 0.5 ETH from Ethereum to Base"

**Conversions:**
- "Convert 0.1 ETH to WETH"

## Best Practices

- Test with small amounts first
- Specify chain for lesser-known tokens
- Monitor slippage for low-liquidity assets
- Use Base or Polygon to minimize gas (Ethereum mainnet can be expensive)
- Slippage tolerance applied automatically; transactions fail safely if exceeded
