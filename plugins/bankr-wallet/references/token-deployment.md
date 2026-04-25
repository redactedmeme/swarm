# Token Deployment

Deploy ERC20 tokens on Base/Unichain (via Clanker) or SPL tokens on Solana (via Raydium LaunchLab).

## Platforms

| Chain | Platform | Mechanism |
|-------|---------|-----------|
| Base, Unichain | Clanker | Audited ERC20 contracts |
| Solana | Raydium LaunchLab | Bonding curve → pool migration |

## Solana (Bonding Curve)

- Token starts on bonding curve — price increases as more tokens are bought
- Automatically migrates to Raydium pool at graduation
- Creator earns 0.5% trading fees during bonding phase
- Fee Key NFTs grant LP trading fee rights post-migration
- If fee recipient designated: 99.9% to recipient, 0.1% to creator

## EVM (Base / Unichain)

- Straightforward deployment — specify name and symbol
- Audited ERC20 contracts via Clanker
- No bonding curve

## Rate Limits

| Tier | Daily sponsored deploys |
|------|------------------------|
| Standard | 1 |
| Bankr Club | 10 |

Additional deploys require ~0.01 SOL gas payment (Solana).

## Prompts

```
"Deploy a token called REDACTED with symbol REDACTED on Base"
"Launch a Solana token: name=MyToken, symbol=MTK"
"Create an ERC20 on Unichain named Alpha"
```
