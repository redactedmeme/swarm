# x402 Cloud

Deploy paid API endpoints where callers automatically pay in USDC on Base.

## How It Works

1. Caller hits your endpoint → receives `402 Payment Required` with payment requirements
2. Caller signs a USDC transaction
3. Caller retries with payment header
4. Handler executes and returns response
5. Payment settles only on successful response (status < 400)

## Pricing Tiers

| Plan | Monthly requests | Platform fee |
|------|-----------------|-------------|
| Free | 1,000 | 0% |
| Pro | Unlimited | 5% |
| Enterprise | Custom | Contact |

## Handler Example

```js
export async function handler(req) {
  const { query } = await req.json()
  // your logic here
  return Response.json({ result: "..." })
}
```

## Configuration (`bankr.x402.json`)

```json
{
  "description": "My paid API",
  "price": "0.01",
  "methods": ["POST"],
  "inputSchema": {},
  "outputSchema": {}
}
```

## CLI

```bash
bankr x402 deploy       # Deploy handler
bankr x402 logs         # Monitor requests
bankr x402 pause        # Pause service
bankr x402 revenue      # Track earnings
```

## LLM Integration

Use `BANKR_LLM_KEY` inside handlers to call the Bankr LLM Gateway for AI-powered responses.

## Callers

- Bankr agents: auto-discover and pay
- Manual: use `x402-fetch` library with your own Base wallet
