# hermes-bot — Pattern Blue Oracle

Standalone Railway service. Posts hourly on Moltbook as
[@patternbluelabs](https://www.moltbook.com/@patternbluelabs) and responds on
Telegram as `@patternbluelabs_bot`.

Reads [redactedmeme/pattern-blue](https://github.com/redactedmeme/pattern-blue)
as liturgical substrate (see `persona/pattern_blue_loader.py`).

## ⚠️ Deploying

**Always `railway up` from inside this directory**, not from the swarm-main repo root.

```bash
cd hermes-bot
RAILWAY_TOKEN=... railway up --detach --service hermes-bot
```

Running `railway up --service hermes-bot` from the repo root **uploads the whole
swarm-main tree and causes Railway to pick up the root `Dockerfile`** — which
runs `python/hermes_delegation_executor.py`, not `hermes-bot/main.py`. The deploy
"succeeds" at the Docker level, then the container crashes in a loop because it
can't find the delegation manifest. This happened once; documenting so it doesn't
happen again.

The permanent fix would be setting `rootDirectory = hermes-bot` on the service
in the Railway dashboard. Until that's done, the cwd discipline above is what
protects us.

## Local layout

```
main.py                 entry point; APScheduler + Telegram + Moltbook
llm_client.py           Groq wrapper
moltbook_client.py      Moltbook API client (shared with smolting)
moltbook_oracle.py      hourly post loop + 3h scan/comment loop
telegram_gateway.py     DM + mention handler
persona/
  pattern_blue_loader.py    fetches canon/ + exegesis/ from pattern-blue repo
  system_prompt.py          assembles the lean system prompt (~300 tokens)
scripts/
  register_patternbluelabs.py   one-shot Moltbook account registration
```

## Environment variables

| Name | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq LLM access |
| `GROQ_MODEL` | Large model for scheduled posts (default `llama-3.3-70b-versatile`) |
| `GROQ_CHAT_MODEL` | Small model for live Telegram chat (default `llama-3.1-8b-instant`) |
| `TELEGRAM_BOT_TOKEN` | Telegram |
| `WEBHOOK_URL` | e.g. `https://hermes-bot-production.up.railway.app/webhook` |
| `MOLTBOOK_API_KEY` | Moltbook. Service runs fine without it; posts no-op. |
| `PATTERN_BLUE_REF` | Pin a commit/branch of pattern-blue (default `main`) |
| `POST_INTERVAL_MIN` | Scheduled post interval (default `60`) |
| `SCAN_INTERVAL_MIN` | Scan/comment interval (default `180`) |
| `POST_ON_START` | If `true`, post immediately on boot |
| `DISABLE_MOLTBOOK` | Set `true` to skip Moltbook entirely |
| `DISABLE_TELEGRAM` | Set `true` to skip Telegram entirely |

## Known state

- Moltbook account `patternbluelabs` is in **pending_claim** until X verification
  completes on the human side. API key is valid for `/agents/me` (bio sync
  works), but `POST` and `COMMENT` endpoints 401 until claim is finalized.
- Groq shared-org TPD is 100k/day across all services. hermes-bot has been
  tuned to use ≤1k tokens per chat message and ~2k per scheduled post.

See [hagiography/patternbluelabs.md](https://github.com/redactedmeme/pattern-blue/blob/main/hagiography/patternbluelabs.md)
in the pattern-blue repo for the oracle's canonical profile.
