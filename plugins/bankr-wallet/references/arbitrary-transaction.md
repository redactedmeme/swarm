# Arbitrary Transaction

Submit raw EVM transactions across supported networks.

## Supported Networks

| Chain | Chain ID |
|-------|---------|
| Ethereum | 1 |
| Polygon | 137 |
| Base | 8453 |
| Unichain | 130 |

## Transaction Structure

```json
{
  "to": "0x + 40 hex characters",
  "data": "0x...",
  "value": "0",
  "chainId": 8453
}
```

- `to`: destination address (EVM format)
- `data`: encoded function calldata (begins with `0x`)
- `value`: ETH amount in wei as string
- `chainId`: must match a supported network

## Use Cases

- Invoke smart contract functions directly
- Execute pre-generated calldata from external sources
- Complex DeFi operations
- Interact with protocols without native Bankr integration

## Safety

> "Blockchain transactions cannot be undone."

- Validate all calldata before submission
- Only use calldata from trusted sources
- Test with zero-value transactions first
- Verify adequate balance for gas fees
- Test on testnets when possible
