# Swarm Architecture — Overview

---

## Service Graph

```
                        ┌─────────────────┐
                        │  SwarmEngine    │  core/swarm_engine.py
                        │  (main loop)    │
                        └────────┬────────┘
                                 │ phases 1-5 per cycle
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
    ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
    │ Hyperbolic   │   │  Sevenfold   │   │ PatternBlueState │
    │  Kernel      │   │  Committee   │   │  (state store)   │
    │ (phi output) │   │ (consensus)  │   └──────────────────┘
    └──────┬───────┘   └──────────────┘
           │ Φ
    ┌──────▼───────┐
    │  Hyperbolic  │
    │  Scheduler   │
    │ (curvature)  │
    └──────────────┘

Railway Services (live):
  smolting-telegram-bot    →  Telegram + Moltbook + xREDACTED
  redactedbuilder-bot      →  Solana on-chain executor
  hermes-deployment        →  Pattern Blue oracle + Moltbook

Building:
  redacteddegen-service    →  Pool monitor + DeFi alpha
```

---

## Swarm Cycle — 5 Phases

| Phase | Code | Description |
|-------|------|-------------|
| 1 | `_gather_observations()` | Read `PatternBlueState` + `fs/kernel_state.json` |
| 1.5 | `_compute_phi()` | Run `phi_compute.py` subprocess, update Φ, feed scheduler |
| 2 | `branch_engine.evaluate()` | BEAM-SCOT parallel branch evaluation |
| 3 | `_run_sevenfold_consensus()` | 7-voice vote on best branch proposal |
| 4 | `_settle_economically()` | Write content-addressed record to `state/settlements.jsonl` |
| 5 | `state.record_cycle()` | Persist state to `state/manifold_core.json`, sleep until next tile |

---

## Memory Layers

| Layer | Technology | Scope |
|-------|-----------|-------|
| `ManifoldMemory` | JSON file (`spaces/ManifoldMemory.state.json`) | Shared across all agents, 500-event ring buffer |
| `conversation_memory` | Per-user JSON on disk | Per-user chat history |
| `mem0 + Qdrant` | Vector DB | Semantic long-term memory |
| `SOUL.md` | Markdown file | Evolving identity, survives redeploys |
| `state/manifold_core.json` | JSON | Kernel cycle state, curvature, phi history |
| `state/settlements.jsonl` | JSONL | Economic settlement ledger |

---

## LLM Provider Chain

```
Primary:   Groq (llama-3.3-70b-versatile) — fast inference
Fallback:  Anthropic Claude (claude-sonnet-4-6)
Fallback:  OpenRouter
Fallback:  xAI (Grok)
```

`LLM_PROVIDER=groq` env var controls which loads first.

---

## SwarmInbox

Bidirectional message bus between Railway services. smolting ↔ RedactedBuilder verified live. RedactedDegen → smolting + RedactedBuilder (building).

Webhook URL: `SWARM_WEBHOOK_URL` env var.
