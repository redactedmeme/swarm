# Terminal Commands — Full Reference

Complete slash-command reference for the swarm terminal (`web_ui/` + `python/`). See [`docs/README.md`](../README.md) for the doc index and [`../../README.md`](../../README.md) for the quick-start.

```
/summon <name>               Load any agent/node as active persona
/unsummon                    Clear active persona, restore base terminal
/invoke <agent> <query>      Send query directly to named agent (no persona change)
/phi  or  /mandala           Summon Φ̸-MĀṆḌALA PRIME (apex node, curvature +3)
/milady [request]            Invoke MiladyNode — VPL, Remilia advisory
/agents                      List all agents by tier (CORE / SPECIALIZED / GENERIC)
/agents find <query>         Search agents by name, role, or capability
/agents consolidate          Generic agent consolidation report

/committee <proposal>        Live Sevenfold Committee (7 parallel Groq calls, 71% supermajority)

/observe pattern             Live 7-dimension Pattern Blue readout + Φ_approx
/observe <target>            Curvature observation on any node, agent, or concept
/resonate <frequency>        Tune to a harmonic layer of the lattice
/organism                    Hyperbolic manifold organism status

/shard <concept>             Generate concept shard + auto-draft tweet for review
/tweet draft                 Preview queued tweet draft
/tweet confirm               Post queued tweet via ClawnX
/tweet discard                Discard queued tweet draft

/remember <text>             Store a memory (semantic, Mem0/Qdrant)
/recall <query>              Semantic search over stored memories
/mem0 status                 Memory system availability + config
/mem0 add <text>             Explicit memory add
/mem0 search <query>         Explicit semantic search
/mem0 all [limit]            List recent memories
/mem0 inherit <id>           Copy memories from another agent session

/contract status             View current interface contract state
/contract propose <change>   Submit proposal to live NegotiationEngine
/contract history            List contract version snapshots
/contract sync               Force kernel-contract manual sync
/bridge status                Kernel-Contract bridge diagnostic
/sigil log [N]                Recent forged sigils from ManifoldMemory (default: 5)
/sigil stats                  Aggregated SigilPactAeon statistics
/sigil verify <tx>            Verify sigil by tx hash prefix
/docs <query>                 Semantic search over Pattern Blue docs (RAG)

/skill list                   List installed skills
/skill use <name>             Activate a skill in this session
/skill install <repo>         Install a skill from GitHub
/skill deactivate             Deactivate current skill(s)

/token <address>              Token analytics (Clawnch)
/leaderboard                  Token leaderboard
/search <query>                Search tweets via ClawnX
/timeline                     Home timeline
/user <@handle>                User profile lookup

/scarify <payer> <amt>         Issue x402 scarification token (base / deeper / monolith)
/pay                            x402 payment info: price sheet, treasury address, settlement flow

/space list                     List available spaces
/space <name>                    Load a specific space
/node list                       List all nodes
/node summon <name>              Spawn a node as persistent subprocess

/status                          Swarm session state (Phi_approx, curvature, kernel vitality)
/config beam <3-6>               Set Beam-SCOT beam width (default: 4)
/help                            Full command reference
```
