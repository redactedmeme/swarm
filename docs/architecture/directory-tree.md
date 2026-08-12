# Full Directory Tree

Detailed file-by-file breakdown. Root [`README.md`](../../README.md) has the condensed top-level map; each service also has its own README with this level of detail (e.g. [`redacted-chan-bot/README.md`](../../redacted-chan-bot/README.md)).

```
swarm/
├── redacted-chan-bot/          Relational companion agent (Telegram + web chat)
│   ├── main.py                 Bot entry + echo handler
│   ├── data_proxy.py           Internal HTTP API
│   ├── soul_manager.py         SOUL.md identity layer
│   ├── long_context_optimizer.py  Multi-tier memory compression
│   ├── relationship_arc.py     Weekly narrative arc + pinned moments
│   ├── conversation_affect_tracker.py  Turn-by-turn emotional arc
│   ├── arc_context_feed.py     Trajectory-triggered memory surface
│   ├── thread_linker.py        Prior-session topic detection
│   ├── proactive_messenger.py  Outbound agency scheduler
│   ├── session_continuity.py   Session momentum + next_thread
│   ├── redis_state_cache.py    Momentum persistence (Redis)
│   ├── hermes_dispatch.py      SwarmInbox task delegation to Hermes
│   ├── scheduled_routines.py   22 autonomous routines
│   └── llm/cloud_client.py     Multi-provider client (routes via proxy)
│
├── hermes-bot/                 Operational agent (web, code, infra control)
│   ├── main.py
│   ├── skill_memory.py         JSONL skill store
│   └── plugins/swarm-manager/
│       ├── swarm_manager.py    Groq tool-calling loop
│       ├── web_tools.py        web_fetch + web_search
│       ├── exec_tools.py       python_exec sandbox
│       └── skill_tools.py      skill_recall
│
├── redacted-proxy/             OpenAI-compatible LLM privacy proxy
│   └── main.py                 aiohttp, /v1/chat/completions, local log
│
├── webchat/                    Private web chat interface
│   ├── server.py               FastAPI (JWT auth, /upload, rate limit)
│   └── static/index.html       Chat UI (TTS, file + image upload)
│
├── smolting-telegram-bot/      CT agent (Moltbook, HTC, Clawbal)
│   ├── main.py
│   ├── moltbook_autonomous.py  Autonomous Moltbook posting + engagement
│   └── llm/cloud_client.py
│
├── agents/                     elizaOS-compat .character.json definitions
├── nodes/                      Specialized node definitions
├── python/
│   ├── redacted_terminal_cloud.py
│   ├── groq_beam_scot.py       Real parallel BEAM-SCOT (N branches)
│   ├── groq_committee.py       Sevenfold Committee (7 voices, 71% supermajority)
│   ├── gnosis_accelerator.py   Meta-learning node
│   └── ...
├── skills/                     Claude Code skill modules (SKILL.md)
├── spaces/                     Persistent thematic environments
├── kernel/
│   └── hyperbolic_kernel.py    {7,3} hyperbolic manifold + organism
└── run.py                      Unified entry point
```
