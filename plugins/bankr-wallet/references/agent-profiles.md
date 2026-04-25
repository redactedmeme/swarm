# Agent Profiles

Public showcase pages at `bankr.bot/agents` for projects that have deployed tokens via Bankr.

## Requirements

Must have deployed a token through Bankr (Doppler or Clanker) or be a fee beneficiary on the token.

## Fields

| Field | Required | Limit |
|-------|---------|-------|
| Project name | ✅ | — |
| Token address | ✅ | — |
| Description | optional | 2,000 chars |
| Team members | optional | 20 max |
| Products | optional | 20 entries |
| Revenue sources | optional | — |

## CLI

```bash
bankr agent profile create
bankr agent profile update
bankr agent profile delete
bankr agent profile add-update   # Add project update
```

## REST API

Endpoints under `/agent/profile` — requires API key authentication.

## Visibility

Profiles start unapproved and invisible. After admin approval:
- Appear in public listings
- Market cap updates every 5 minutes
- Revenue updates every 30 minutes
- LLM usage statistics shown
- Recent tweets from linked Twitter account
- Real-time WebSocket updates

## Public Endpoints

Browse profiles by token address or slug — no auth required.
