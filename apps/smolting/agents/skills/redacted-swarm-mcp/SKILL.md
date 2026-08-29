---
name: redacted-swarm-mcp
description: >
  REDACTED AI Swarm HTTP MCP surface exposed by smolting-telegram-bot (dashboard webhook server).
  Tools broadcast, alpha, committee, phi, skills_list, skills_read - use when driving the Telegram
  bot, Pattern Blue committee, or loading agentskills-style prompts from agents/skills.
---

# REDACTED Swarm MCP (HTTP)

When the smolting bot runs with `WEBHOOK_URL`, the same port exposes MCP-compatible JSON:

- `GET /mcp` — server metadata
- `GET /mcp/tools` — tool schemas
- `POST /mcp/call` — body `{"name": "<tool>", "arguments": {...}}`

Set header `Authorization: Bearer <SWARM_API_TOKEN>` when the deployment uses `SWARM_API_TOKEN`.

## Tools (remote)

| Tool | Role |
|------|------|
| `broadcast` | Post text to Telegram (group via `ALPHA_CHAT_ID` or `chat_id` in args) |
| `alpha` | Trigger scheduled daily-alpha job |
| `committee` | Run 3-voice Pattern Blue vote on a `proposal` |
| `phi` | Ingest Φ metric; optional `alert` → group warning |

## Tools (local bundle)

| Tool | Role |
|------|------|
| `skills_list` | List skill ids + names + descriptions from `agents/skills/*/SKILL.md` |
| `skills_read` | Args: `skill_id` — return full SKILL.md body for one skill |

## Local stdio MCP (Cursor / Claude Code)

From repo: `pip install mcp pyyaml requests` then:

`python swarm_mcp_stdio.py`

- Loads **skills** from disk (same `agents/skills` tree).
- Proxies **broadcast / alpha / committee / phi** to `SWARM_MCP_HTTP_URL` (your Railway URL) using `SWARM_API_TOKEN`.

Optional: `SWARM_SKILLS_EXTRA_DIRS` — extra `PATHSEP`-separated roots for more `SKILL.md` trees (monorepo).
