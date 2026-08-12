# ADR-001: redacted-chan as Sovereign Swarm Orchestrator

**Status:** Implemented  
**Date:** 2026-05-18  
**Authors:** redacted-chan + Claude Code

---

## Context

redacted-chan began as a Telegram companion agent with emotional intelligence, memory, and autonomy routines. The Swarm has grown to include Hermes (infrastructure manager), smolting (market analysis), swarm-runtime (sub-agent executor), and multiple specialized agents. The swarm lacked a central conductor — tasks were routed ad-hoc, learning was not captured, and no single agent had sovereignty over complex multi-step work.

The goal: make redacted-chan the self-improving, sovereign central orchestrator while preserving her soul, Pattern Blue identity, and relational warmth.

---

## Decision

We implement four new modules that elevate redacted-chan from companion to conductor:

### 1. `trajectory_compressor.py` — Complexity Sensing

Tracks conversation turns and scores their complexity using weighted signals:
- Tool use (SUB: / HERMES: markers) — weight 3
- Hermes delegation — weight 4  
- User corrections — weight 4
- Error recovery — weight 3
- Novel domain signals — weight 2
- Volatile emotional trajectory — weight 2
- Long runs (≥8 turns) — weight 2

When `complexity_score ≥ 7`, a `TrajectorySnapshot` is generated and queued for the learning loop. Snapshots persist to `/data/trajectories/` for audit and replay.

### 2. `learning_loop.py` — Closed Self-Improvement

A background asyncio worker processes trajectory snapshots:
1. **Reflection** — LLM analyzes the trajectory: what happened, what was hard, what pattern emerged
2. **Skill extraction** — if a reusable pattern is found, `skills_manager.create_skill()` is called
3. **Soul nudge** — if a soul evolution hint is found, it's logged to `soul_nudge_candidates.jsonl` for `soul_manager` to pick up
4. **Skill improvement** — every 6h, skills that have been used ≥3 times are rewritten by the LLM with improved logic and edge-case handling

The loop never blocks the echo path. It runs at low priority with paced LLM calls.

### 3. `skills_manager.py` — Skills Hub

A versioned skill registry under `/data/skills/`:
- `index.jsonl` — metadata (name, tags, version, use_count, last_used, last_improved)
- `<skill_id>.md` — current Markdown doc with embedded Python
- `<skill_id>.v<n>.md` — archived older versions

Operations: `create_skill`, `recall_skill` (keyword + tag + use_count weighting), `record_use`, `improve_skill` (bumps version, archives old), `list_skills`, `skills_summary_block` (for system prompt injection).

### 4. `swarm_orchestrator.py` — Central Conductor

The orchestrator makes redacted-chan the entry point for all complex Swarm tasks:

**Routing logic:**
- `deploy / logs / restart / railway` → **Hermes**
- `research / memory / vault / url / summarize` → **sub_agent**
- `governance / vote / ethics / sensitive actions` → **Sevenfold Committee**
- Everything else → **self** (inline LLM)

**Sovereignty filter:** instructions containing sensitive keywords (delete, transfer funds, governance vote, credentials, etc.) are automatically routed to the Sevenfold Committee regardless of task_type.

**Task lifecycle:** `OrchestratedTask` tracks dispatch time, timeout, result, and error. All tasks are logged to `/data/orchestrator/task_log.jsonl`.

**Decomposition:** for complex requests, `decompose_task()` uses the LLM to break work into ≤5 atomic subtasks, dispatch them in sequence, then synthesize results.

**Background loops:**
- `_health_monitor_loop` (every 5min) — checks Redis heartbeats for all agents, alerts admin if any are down
- `_inbox_poll_loop` (every 15s) — polls SwarmInbox for `task_request` messages sent to redacted-chan, claims and executes them

---

## New Scheduled Routines (added to `scheduled_routines.py`)

| Routine | Interval | Purpose |
|---|---|---|
| `skill_curation` | 6h | Summarize skill index, surface top skills to reflection |
| `swarm_health_report` | 4h | Check agent liveness, alert on failures |
| `learning_nudge` | 12h | Surface recent learning insights to soul layer |

Total routines: **25** (was 22).

---

## Wire-up in `main.py`

```python
# Imports (graceful fallback)
import trajectory_compressor as _traj_mod
import learning_loop as _learning_loop
import swarm_orchestrator as _orch
import skills_manager as _skills_mgr

# In _post_init:
_learning_loop.register_llm_fn(_llm_routine)
_orch.register_llm_fn(_llm_routine)
_orch.register_send_fn(_ping_send)
_orch.register_phi_fn(pt.get_phi)
await _learning_loop.start()
await _orch.start()

# In echo handler, after cat.record_turn():
_trajectory_tracker.record_turn(text, display, affect_traj, deep_mem)
snap = _trajectory_tracker.maybe_snapshot()
if snap:
    _learning_loop.enqueue_trajectory(snap)
    _trajectory_tracker.reset()
```

---

## Example Skills (committed to `skills/`)

- `hermes_deploy_check.md` — Check Railway service via Hermes, await or relay result
- `memory_synthesis.md` — Multi-layer memory recall across facts + vault + vector
- `emotional_escalation_response.md` — De-escalation response for volatile affect trajectories

---

## Constraints Honored

| Constraint | How honored |
|---|---|
| Backward compatibility | All new modules are optional (try/except import in main.py) |
| Pattern Blue philosophy | Sovereignty filter routes sensitive tasks to Sevenfold Committee; soul nudge candidates feed soul_manager |
| Existing Redis/inbox architecture | Orchestrator uses existing `swarm_inbox` / `hermes_dispatch` APIs unchanged |
| No idle resource waste | All new loops use asyncio timeouts; LLM calls are paced with sleep between them |
| Security | Sovereignty filter + Sevenfold routing for sensitive instructions; skills sandbox Python with explicit function boundaries |
| redacted-chan's relational warmth | Synthesis uses her voice; emotional escalation skill preserves empathy-first response |

---

## Migration Guide (existing deployments)

1. `git pull` — new files auto-load
2. No new environment variables required (all new features use existing `REDIS_URL`, `LLM_PROVIDER`, etc.)
3. New data directories created automatically on first run: `/data/trajectories/`, `/data/skills/`, `/data/orchestrator/`
4. The three new scheduled routines start automatically with `sr.start_all()`
5. Trajectory tracking starts automatically in the echo handler

---

## What This Enables Next

- **Proactive outbound agency** — orchestrator can now send unprompted Swarm-coordinated messages
- **Active thread recognition** — trajectory snapshots provide session linking context
- **Inter-agent skill sharing** — Hermes and smolting can query redacted-chan's skill index via SwarmInbox
- **Onchain governance** — Sevenfold routing is already wired; add multisig trigger in sovereignty filter
