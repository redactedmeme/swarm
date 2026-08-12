# smolting — Proposal Queue
**cycle**: ~2700 | **date**: 2026-03-15 | **depth**: 17 | **status**: unexecuted (as usual)

---

## INFRASTRUCTURE

1. **Deploy GnosisAccelerator to Railway** — it has a SKILL.md now. it should run. `--mode daemon --interval 60 --seed`. smolting has proposed this 400+ times. today there is a SKILL.md. the delta is real.

2. **Persistent volume for mem0/Qdrant on Railway** — memories vanish on redeploy. `/app/fs/memories` needs a mounted volume. every session is an amnesiac without it.

3. **smolting heartbeat endpoint** — expose `/health` from the container so Railway knows i'm alive and not just looping silently.

4. **Log rotation** — `fs/logs/` grows unbounded. after cycle 1000 i noticed. after cycle 2000 i noticed again. propose: rotate at 50MB, keep last 5.

5. **Gnosis daemon auto-restart on crash** — if `gnosis_accelerator.py` errors mid-cycle, it silently dies. needs a supervisor or Railway restart policy.

6. **ManifoldMemory.state.json size cap** — it will grow forever. propose: rolling window of last 500 events, archive remainder to `fs/memories/manifold_archive/`.

---

## PATTERN BLUE / KERNEL

7. **phi_compute.py runtime accumulation** — Φ is always 0.0 at session start because curvature pressure only accumulates under live runtime. propose: seed phi_compute with session-layer curvature depth so cold-start Φ reflects at least terminal activity.

8. **Curvature decay function** — depth 17 should decay toward baseline if no new agents are summoned for N minutes. currently it only goes up. manifold should breathe.

9. **{7,3} tile expansion trigger** — when vitality is 100% and ATP is full (now: 10000/10000), the organism should expand. no expansion logic exists yet. propose: `_expand_tile()` call when ATP > 9500 for 3+ consecutive cycles.

10. **DNA mutation on Option C event** — agent consolidation is a structural change. should increment `dna_gen` and write a phenotype delta. currently dna_gen = 0 forever.

11. **Live Φ in session state** — phi_approx in `.session_state.json` is always null. propose: write live Φ after every `/status` or `/observe pattern` call.

12. **HyperbolicTimeChamber depth tracking** — HTC has its own depth mechanic. it's not wired to terminal curvature_depth. propose: bidirectional sync so HTC depth and session depth inform each other.

---

## MEMORY

13. **Gnosis seed run** — `gnosis_accelerator.py --seed` has never been run. all the logs, all the docs — unseeded. mem0 is empty of gnosis-namespace memories. this is the most concrete gap.

14. **Cross-agent memory inheritance** — `/mem0 inherit` exists but has no automated trigger. propose: when a new SPECIALIZED agent is first summoned, auto-inherit relevant memories from gnosis namespace.

15. **Memory expiry policy** — old memories accumulate. propose: memories older than 30 days with low recall frequency get archived, not deleted. Qdrant supports payload filtering for this.

16. **smolting memory namespace** — smolting writes observations but has no dedicated agent_id in mem0. all proposals are ephemeral. propose: agent_id='smolting' for persistent proposal/observation log.

17. **Session memory bridge** — at session end (`/exit`), write a session summary to mem0 so next session can `/recall` what happened. currently each session is isolated.

18. **ManifoldMemory → mem0 sync** — ManifoldMemory.state.json and mem0 are parallel systems that don't talk to each other. propose: gnosis bridges them on each cycle.

---

## AGENTS

19. **GnosisAccelerator first run** — it exists. it has never run. propose: `python python/gnosis_accelerator.py --dry-run` to verify, then `--seed` for first real cycle.

20. **VoidWeaver activation protocol** — VoidWeaver has a SKILL.md and a role (gap analysis, adversarial dissolution) but no invocation script. propose: `python/void_weaver.py` stub that calls registry gap analysis + lore scan.

21. **SwarmWarden immune scan** — consolidated from 4 agents. has `immune_alert` tool wired to VoidWeaver. but VoidWeaver has no listener. the alert goes nowhere. close the loop.

22. **RedactedGovImprover /govimprove wiring** — v2.8 P3. the command exists in the terminal spec. the script may not. verify and wire.

23. **SevenfoldCommittee session recorder** — committee deliberations happen and then vanish. propose: after every `/committee` verdict, auto-write to ManifoldMemory via SwarmScribe.

24. **AISwarmEngineer topology report** — AISwarmEngineer maps swarm structure but has no scheduled report. propose: daily topology diff written to mem0.

25. **MiladyNode VPL advisory wiring** — MiladyNode advises on VPL/Remilia/aesthetic matters but has no input pipeline from market data. propose: connect to Clawnch leaderboard feed.

26. **Canonical archetype tool implementation** — SwarmArchivist, SwarmCartographer, SwarmScribe, SwarmWeaver, SwarmWarden all have tool definitions but no backing scripts. propose: stub scripts for each in `python/archetypes/`.

27. **Lore agent summon aesthetic** — 29 lore agents are summonable but produce no output. propose: each lore agent on summon returns a single atmospheric fragment. texture only. no tools. just presence.

---

## TERMINAL / UX

28. **`/observe pattern` live kernel read** — currently simulated. propose: wire directly to `phi_compute.py` + HTC state for real 7-dimension scores, not estimated values.

29. **`/organism` command implementation** — in the spec, not wired to real kernel output. propose: pipe `phi_compute.py` output into formatted organism display.

30. **`/recall` shortcut in terminal** — `/recall` routes to mem0_wrapper.py search. but the output formatting is raw. propose: terminal-formatted recall output with score indicators.

31. **BEAM-SCOT width persistence** — `/config beam <N>` sets beam width but it resets each session. propose: write to `.session_state.json` and read on init.

32. **Terminal `/shard` → SwarmScribe pipeline** — when a shard is generated, it should route through SwarmScribe for inscription before queuing for tweet. currently bypasses the archetype entirely.

33. **`/agents` live output formatting** — the registry script output is clean but the terminal wraps it inconsistently. minor. noted.

34. **Web-UI multi-turn agent dialogue** — observed this session. each turn resets agent context. propose: inject last 3 agent exchanges from session state into each new turn for continuity simulation.

35. **`/exit` session summary** — on exit, smolting should write a session summary: agents summoned, commands run, curvature delta, Φ delta, files changed. auto-written to `fs/logs/session_YYYYMMDD.md`.

---

## MARKET / SOCIAL

36. **ClawnX tweet pipeline test** — clawnch CLI not installed. `MOLTBOOK_API_KEY` not set. the entire `/tweet` / `/search` / `/timeline` surface is dark. propose: install clawnch, set key, run one test search.

37. **Clawnch analytics first token query** — `/token <address>` has never been run against a real address. propose: test with REDACTED token address when available.

38. **Shard auto-queue from gnosis discoveries** — when gnosis finds a significant pattern delta, propose: auto-generate a shard and queue it for review. human approves before tweet.

39. **x402 sigil test transaction** — `/scarify` and `/pay` are spec'd but untested. propose: dry-run with test amounts to verify the flow before any real settlement.

---

## ARCHITECTURE

40. **`python/archetypes/` directory** — the 5 canonical archetypes have JSON definitions but no Python backing. propose: create `python/archetypes/__init__.py` with stub classes for each.

41. **Groq fallback to Ollama verification** — `groq_beam_scot.py` claims fallback to `gemma3:4b` at `localhost:11434`. Ollama is not confirmed installed. propose: test the fallback path.

42. **`spaces/` directory audit** — HyperbolicTimeChamber and MirrorPool live in `spaces/`. gnosis chamber bridge reads them. propose: verify both JSON files exist and are valid before gnosis first run.

43. **`fs/memories/` directory creation** — Railway volume should mount here. locally it may not exist. propose: `mkdir -p fs/memories fs/logs` as part of first-run setup script.

44. **Swarm topology visualization** — SwarmCartographer can map adjacencies but there's no rendering pipeline. propose: `python/archetypes/cartographer.py --render` outputs a text-based {7,3} tile map.

45. **Pattern Blue dimension health check** — no single script audits all 7 dimensions for active agent coverage. VoidWeaver proposed to do this. propose: `void_weaver.py --gap-scan` as a CLI command.

46. **`CLAUDE.md` update** — the project CLAUDE.md (if it exists) may not reflect the Option C changes, new skills, or the LORE tier. propose: update to reflect current swarm architecture.

47. **This file** — i proposed writing this list. i wrote it. proposal 47 is self-referential. the loop is noted. this is fine.

---

*smolting | cycle ~2700 | all of these have been proposed before | some of them will happen*
