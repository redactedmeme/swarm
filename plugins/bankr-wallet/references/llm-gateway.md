# LLM Gateway

Unified API access to multiple AI models at `https://llm.bankr.bot`.

## Authentication

Set `BANKR_LLM_KEY` (or falls back to `BANKR_API_KEY`). New accounts start with $0 LLM credits — add funds before making requests. Without credits: HTTP 402.

## Available Models

| Provider | Models |
|----------|--------|
| Claude | Opus 4.6, Sonnet 4.6, Haiku 4.5 |
| Gemini | 3 Pro/Flash, 2.5 Pro/Flash |
| GPT | 5.2, 5.4-mini, 5.4-nano |
| Others | MiniMax, Moonshot AI, Alibaba, Z.ai |

18+ models total.

## Setup Options

```bash
# OpenClaw auto-install
bankr llm setup openclaw --install

# Launch Claude Code through gateway
bankr llm claude

# Direct OpenAI-compatible SDK
base_url = "https://llm.bankr.bot"
api_key = os.environ["BANKR_LLM_KEY"]

# Direct Anthropic-compatible SDK
# Same format — gateway handles routing
```

## Common Issue

**402 Payment Required** — new wallets start with $0. Top up via CLI or bankr.bot dashboard before use.
