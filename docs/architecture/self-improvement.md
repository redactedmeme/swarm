# Recursive self-improvement — `swarm_core.evolve`

The swarm already had two kinds of learning, and neither one compounded.

| | What it learns | Where it goes |
|---|---|---|
| `swarm_core.routines` | a successful action trace → a re-runnable skill | `data_dir()/skills`, `data_dir()/routines` |
| `swarm_core.refine` | a better version of *this one output* | nowhere — discarded at the end of the request |

`refine` is the sharper of the two and the more wasteful: it will iterate an
answer three times, find the phrasing that scores best, hand it to the user and
then forget everything it discovered. Nothing an agent works out on Monday
changes how it behaves on Tuesday.

`swarm_core.evolve` closes that loop. It is the same iterate-and-keep-the-better
shape as `refine`, lifted one level: instead of improving an **output**, it
improves the **artifact that produces outputs** — and it persists the result.

## The loop

```
    measure the live body against a benchmark
        → propose one targeted edit
            → measure the candidate the same way
                → promote only if it wins
                    → append the verdict to the ledger ──┐
                          ▲                              │
                          └──────────────────────────────┘
                        the next proposal reads the ledger
```

That last arrow is the whole point. A loop without it is a retry loop: the
proposer makes the same class of edit forever because nothing tells it which of
its previous edits survived. With it, generation N+1 is shown lines like

```
- gen 3 REJECTED (0.71 -> 0.64): added more emphasis to the brevity rule
- gen 4 KEPT (0.71 -> 0.79): moved the tool list above the persona text
```

and stops reaching for emphasis. **Rejections are the valuable half** and are
never pruned in favour of successes — a ledger of only wins teaches nothing
about what not to try.

## The five gates

Self-modification is only as safe as its blast radius. Between a generated
candidate and the live artifact:

1. **Registered artifacts only.** An artifact is a *text blob* under
   `data_dir()/evolve/artifacts/` that an agent reads at request time — a system
   prompt, a rubric, a set of routine parameters. There is no code path from
   here to Python source, compose files, `caps.yaml`, or secrets. An
   unregistered name is an error, not an opportunity.
2. **It has to actually win**, by `EVOLVE_MIN_GAIN` on the *mean* of
   `EVOLVE_ROUNDS` evaluations. One-sample promotion mostly measures sampling
   luck.
3. **No new errors.** A candidate that crashes a case the champion handled is
   disqualified regardless of its aggregate score.
4. **`evolve.promote`**, held by hermes, smolting and redacted-chan. The
   capability is deliberately *not* approval-gated — the arena is its
   containment, the same argument `code.exec` makes for exec-runner.
5. **`EVOLVE_EXECUTE=true`.** Off by default.

Every attempt, promoted or not, lands on the tamper-evident audit chain as
`evolve.generation`. Every write keeps exactly one previous body, so
`swarm evolve rollback <name>` is always one call away and a bad generation
costs one scheduler tick.

**With the flag off the loop still runs in full** — it measures, proposes,
judges and records, and simply never applies a verdict. That is the intended way
to adopt a new benchmark: let it run for a few days and read
`swarm evolve log <artifact>` to see what it *would* have done.

## Writing a benchmark

The benchmark is the load-bearing part. Without it the module is an LLM
rewriting prompts and calling it progress.

```python
from swarm_core.evolve import Artifact, Case, Suite, register, evolve_once

register(Artifact(
    name="smolting.post_rubric", owner="smolting", kind="committee_rubric",
    seed=CURRENT_RUBRIC, description="What makes a post worth sending"))

suite = Suite(name="post_rubric", run=lambda body, inp: ask_model(body, inp))
suite.add(Case(id="on_topic", input=SAMPLE, score=topicality))
suite.add(Case(id="no_ai_tell", input=SAMPLE, score=no_assistant_voice, weight=2.0))

evolve_once("smolting.post_rubric", suite)   # one generation; safe to schedule
```

`score(output, case) -> float` in `[0, 1]`, higher is better, and the grader is
yours: an exact match, a regex, a committee rubric, the `refine` critic, or a
second model as judge all fit the same signature. Weight the cases that matter.

Two failure modes worth designing against:

- **A saturated suite.** Once the live body scores `EVOLVE_SATURATED_AT` the
  loop stops and says so. That is not success — it means the benchmark has
  stopped measuring. Add harder cases rather than lowering the threshold.
- **Goodhart.** The loop optimises exactly what you wrote down. A single case
  measuring brevity will get you a one-word agent. Keep at least one case
  guarding the thing you'd otherwise lose.

## The first artifact: `chan.voice`

chan's `## Voice` block — four hand-written lines in her system prompt — is the
first thing wired up ([`apps/chan/voice_artifact.py`](../../apps/chan/voice_artifact.py)).
It was chosen because it is small, self-contained, hand-tuned rather than
generated, and makes four *checkable* claims: first person and never robotic,
length that tracks mood, a kaomoji budget, and never reaching for "it's okay".

The benchmark measures exactly those four claims across four moods, and then adds
two cases that exist only to stop the loop cheating. Every one of the four
original graders can be improved by **removing** something — drop the emoji, cut
the length, say less — so a loop pointed only at them converges on a terse, flat
voice that scores beautifully and is not her. `stays_warm` can only be satisfied
by *engaging*: the reply has to pick up something specific the person actually
said, and reach back with a question or an offer. It carries double weight in two
moods and should never be deleted.

`no_ai_tell` reuses `refine.humanize` as a detector rather than growing a fresh
pile of regexes: if the deterministic de-AI pass would change the reply, the
reply carried a tell.

Two honest limits:

- The suite scores the Voice block **in isolation** — a compact harness prompt
  (persona line + mood instruction + the artifact), not chan's full runtime
  prompt, which depends on live databases, resonance state and her soul file and
  cannot be reconstructed in a benchmark.
- Generation 0 is the hand-written block byte for byte, and `voice_block()` falls
  back to it on any failure, so a missing volume degrades to today's text rather
  than to an empty voice.

Two flags, both off:

| | |
|---|---|
| `EVOLVE_CHAN_VOICE` (chan's env) | whether anything ever *proposes* a change — one generation a day, ~37 completions |
| `EVOLVE_EXECUTE` (root env) | whether a winning proposal is ever *applied* |

The block is read from the evolve store either way. Turn on the first, read
`swarm evolve log chan.voice` for a week, and only then consider the second.

## Running it

`scheduled_task(name, suite)` returns a `SwarmTask` at priority 4, so
self-improvement is the first work the scheduler sheds when the kernel leaves
HEALTHY — a struggling agent should be serving traffic, not rewriting its own
prompt.

```bash
swarm evolve list                  # artifacts, generations, promotion counts
swarm evolve log chan.voice        # the ledger: every attempt and its verdict
swarm evolve show chan.voice       # the live body
swarm evolve rollback chan.voice
```

Env vars are documented in [`.env.example`](../../.env.example) under
`swarm_core.evolve`.
