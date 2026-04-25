# Safety & Access Control

## API Key Format

All Bankr keys use format `bk_...` with capability flags:
- `walletApiEnabled` — enables write operations (transfer, sign, submit)
- `readOnly` — when true, filters write tools; sign/submit return 403
- `allowedIps` — CIDR or individual IPs; empty array = all IPs allowed

Manage keys at [bankr.bot/api](https://bankr.bot/api).

## Separate Keys

One key can handle both Agent API and LLM Gateway, or configure distinct keys for different permissions/rate limits.

## Rate Limits

| Tier | Daily messages |
|------|---------------|
| Standard | 100 |
| Bankr Club | 1,000 |

Rolling 24-hour window from first message (not midnight reset).

## Deployment Checklist

- [ ] Dedicated agent wallet (not personal)
- [ ] Limited funds — only what the agent needs
- [ ] `readOnly: true` if no write ops needed
- [ ] API key in environment variable, never source code
- [ ] IP allowlist configured for server deployments
- [ ] Rotate keys periodically; revoke immediately if compromised

## Key Principle

> "A compromised agent key only exposes the agent wallet's funds, not your main holdings."

Always use dedicated agent accounts for autonomous systems.

## Transaction Safety

- All blockchain transactions are permanent once confirmed
- Verify addresses before sending
- Test with small amounts before scaling
- Keep gas buffer of native tokens (don't use entire balance for trades)
