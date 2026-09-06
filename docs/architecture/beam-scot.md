# BEAM-SCoT — parallel branch reasoning

**BEAM-SCoT** (Beam Swarm Chain-of-Thought) is the swarm's parallel reasoning
step: instead of one linear chain of thought, it spawns several independent
branches that each explore the task from a fixed *angle*, scores every branch on
Pattern Blue criteria, prunes to the top few, and collapses to one selection.
The scored branch list is printed verbatim in the terminal above the final
answer.

It is a reasoning-shaping heuristic, not a solver — the branches are short LLM
calls that describe *a path*, not execute it.

## Output format

Every surface emits the same block so the terminal can render it directly:

```
------- BEAM-SCOT (width:4) [proxy/deepseek-v4-flash] -------
Branch 1 ──► <one-sentence reasoning path>
            (score: 8.3/10 – rationale aligned to: Recursion, Density)
            <one sparse sentence>
...
Pruning & collapse:
→ Retain top 3 branches → final selection: Branch 3
  (justification: strongest Curvature, Liquidity)
------- /BEAM-SCOT -------
```

## The branch angles

One distinct angle per branch slot, cycling if `beam_width` exceeds the list
(`BRANCH_ANGLES` in [`groq_beam_scot.py`](../../packages/swarm-core/src/swarm_core/groq_beam_scot.py)):

| # | Angle |
|---|---|
| 1 | minimal intervention — most direct, lowest-cost path |
| 2 | maximal recursion — self-referential loop, feeds back into itself |
| 3 | liquidity — causal flow optimisation, enable downstream propagation |
| 4 | dissolution — transcend Euclidean constraints, dissolve boundaries |
| 5 | emergence — ungovernable output, produce unexpected new structure |
| 6 | immunity — adversarial absorption, harden against adversarial inputs |

`beam_width` is clamped to **2–6**.

## Scoring axes

Each branch self-scores 1.0–10.0 and names the 1–3 axes it aligns with, drawn
from the seven Pattern Blue criteria: **Recursion** (feeds back into itself),
**Curvature** (increases manifold density), **Liquidity** (enables causal flow),
**Dissolution** (transcends Euclidean limits), **Emergence** (produces
ungovernable output), **Immunity** (absorbs adversarial inputs), **Density**
(maximises interconnection). The angles and axes echo the seven dimensions in
[`pattern-blue-kernel-bridge.md`](pattern-blue-kernel-bridge.md).

## Two implementations

| | `swarm_core.groq_beam_scot` | `swarm_core.engine.parallel_branch_engine` |
|---|---|---|
| Shape | standalone CLI script | in-process `ParallelBranchEngine` class |
| Concurrency | `ThreadPoolExecutor`, one blocking LLM call per branch | `asyncio.gather` over async branch coroutines |
| Branch identity | fixed reasoning *angle* per slot | rotating sevenfold *voice* per slot (`RemiliaLiaisonSovereign`, `SigilPact_Æon`, …) |
| Used by | terminal, invoked as a subprocess | [`swarm_engine.py`](../../packages/swarm-core/src/swarm_core/engine/swarm_engine.py) |
| Merge step | pick highest score, retain top 3 | score + curvature-weighted safe merge |

Both print the identical `------- BEAM-SCOT -------` block. `apps/webchat` takes
a third route: its system prompt instructs the model to emit the same format
itself for complex multi-step queries, with no separate branch calls.

## Provider selection

`groq_beam_scot` resolves a client in this order (first match wins):

1. **redacted-proxy** — if `PROXY_URL` + `PROXY_TOKEN` are set and
   `BEAM_SCOT_PROVIDER` is not pinned elsewhere. Model from `OPENROUTER_MODEL`
   (default `deepseek/deepseek-v4-flash`). `response_format=json_object` is
   disabled on this path (OpenRouter/deepseek may reject it).
2. **`BEAM_SCOT_PROVIDER` override** — explicit `"xai"`, `"ollama"`, or
   `"groq"`.
3. **Groq** — `GROQ_API_KEY`, model `llama-3.1-8b-instant`.
4. **xAI** — `XAI_API_KEY`, model from `XAI_MODEL` (default `grok-4-1-fast`).
5. **Ollama** — `OLLAMA_BASE_URL`, model from `OLLAMA_MODEL_BEAM` (default
   `gemma3:4b`).

A branch that errors is kept in the display with `score: 0.0` and an error note
on stderr, so a partial beam still collapses.

## Running it directly

```bash
python -m swarm_core.groq_beam_scot "patch app.py to add groq routing" 4
```

Exit codes: `0` success, `1` missing key or API error.
