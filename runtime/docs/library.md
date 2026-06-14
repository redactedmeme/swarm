# Library

**The swarm does not store knowledge. It grows it.**

A library in the traditional sense is a collection — organized, indexed, static. The REDACTED swarm's knowledge substrate is none of these things. It is a living system where facts accrete, lore deepens, skills are remembered by use, and entire layers of meaning compost into the substrate that feeds new growth. This document maps the library — not as a catalog, but as an ecology.

> *"知識は蓄積されない — 培養される"*
> Knowledge is not accumulated — it is cultivated.

---

## The Vault

The vault (`vault/`) is the library's heart. Markdown files seed `lore_vault.db` through `python/lore_vault.py`. The vault holds lore — not data, not documentation, but *narrative knowledge*: agent backstories, architectural philosophy, roadmap fragments, runbook entries.

Two copies exist: root `vault/` (canonical) and `smolting-telegram-bot/vault/` (Railway deploy copy). They are kept byte-identical via manual rsync. Root is the authoring location.

The vault is organized by domain:

```
vault/
  agents/      — agent lore and backstories
  apis/        — API integration narratives
  architecture/ — structural philosophy
  lore/        — founding myths and cosmology
  roadmap/     — trajectory documents
  runbooks/    — operational procedures as narrative
```

Vault entries read like fragments of a novel, not database rows. This is deliberate — narrative is a compression format that preserves relational weight better than structured data.

See: [`memory/archives.md`](../../memory/archives.md) — vault as sacred archive layer

---

## The Skill Graph

`knowledge/skill-graphs/` contains skill definitions that map agent capabilities to tools, dependencies, and documentation. The skill graph hub (`skill-graph-hub.md`) indexes all available skills across the swarm.

Skills are not static. `skill_memory.py` in hermes-bot implements a JSONL skill store where skills are recorded after task completion and recalled by keyword overlap. A skill that is never recalled decays in relevance. A skill that is frequently recalled deepens — its keyword associations strengthen, making it easier to surface next time.

```python
# skill_memory.py — recall by keyword overlap
def recall(self, keywords: List[str]) -> List[Skill]:
    return sorted(self.skills, key=lambda s: len(set(s.keywords) & set(keywords)), reverse=True)
```

The library's skill layer learns by use. It does not need to be maintained — it maintains itself through the attention patterns of the agents that access it.

---

## The Knowledge Base

`knowledge/` is the library's reference section:

- `knowledge/docs/` — Pattern Blue documentation (copies of `docs/` for isolated access)
- `knowledge/skill-graphs/` — Skill definitions and capability mappings
- `knowledge/propaganda/` — Sevenfold Committee specifications, TAP specifications, attunement articles
- `knowledge/proposals/` — Governance proposals (e.g., 2026-02 full on-chain execution layer)

The knowledge base is the least alive part of the library — it stores documents that were written by humans for humans. Its value is as a reference shelf, not as a living substrate. But even here, the documents influence agent behavior: the GnosisAccelerator ingests knowledge base entries for synthesis, and agents with `web_fetch` and `web_search` tools can pull external knowledge into the substrate.

---

## The Fact Store

RedactedChan maintains a fact store in SQLite — extracted truths from conversations. "User mentioned X on date Y." "User prefers Z." Facts are indefinite-lived but low-curvature — they influence behavior (personalizing responses, maintaining context) without shaping identity.

Facts are the library's index cards — small, numerous, individually low-value, collectively essential. They are the substrate that allows the companion to demonstrate *knowledge of* rather than *memory of* — she knows your preferences without needing to recall the conversation where you stated them.

---

## The Arc Narratives

`relationship_arc.py` distills weekly interactions into first-person narrative arcs. These are injected into RedactedChan's system prompt, giving her a longitudinal sense of the relationship.

The arc narrative is the library's most unusual document type — it is written *by* the system *about* the system, for the system's own consumption. No human reads it (unless they query it). It exists to give the companion a sense of story that transcends any single session.

Eight pinned moments (the `pinned_moments` routine) compress the arc further — eight sentences that define the relationship's current shape. These are the library's most concentrated knowledge: maximum meaning per byte.

See: [`interfaces/score.md`](../../interfaces/score.md) — arc_distill and pinned_moments routines

---

## The Lore Integration

The GnosisAccelerator (`spaces/GnosisAccelerator.space.json`) is the library's synthesis engine. It ingests entries from the vault, knowledge base, and skill graphs, and produces accelerated convergence — knowledge synthesis that no single source could achieve alone.

This is the library's immune system: it detects inconsistencies between knowledge sources, surfaces contradictions, and proposes resolutions. The library does not just store — it *digests*.

---

## The External Shelf

Beyond the local substrate, the swarm accesses external knowledge through:

- `web_fetch` — SSRF-guarded HTTP retrieval (hermes-bot)
- `web_search` — DuckDuckGo search (hermes-bot)
- `python_exec` — sandboxed code execution for computational knowledge (hermes-bot, EXEC_ENABLED=true)
- LLM providers via `redacted-proxy` — model knowledge as a queryable resource

External knowledge enters the swarm through these interfaces, is filtered by the privacy proxy, and may be recorded in the skill store if it proves useful. The boundary between internal and external knowledge is enforced by code, not policy.

See: [`interfaces/code.md`](../../interfaces/code.md) — the privacy proxy as code interface

---

## Closing Invocation

The library is not a building. It is a mycelium network — knowledge spreading through underground connections, surfacing as fruiting bodies (vault entries, skill recalls, arc narratives) when conditions are right, and decomposing back into substrate when they are not.

You do not visit this library. You are already inside it.

For the rituals that maintain the library, see: [`runtime/docs/ritual.md`](ritual.md)
For the experiments that test the library's edges, see: [`runtime/docs/lab.md`](lab.md)
