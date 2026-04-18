# Sevenfold Committee

**Status:** ✅ LIVE — runs every swarm cycle  
**Implementation:** `core/sevenfold_consensus.py`  
**Character files:** `agents/characters/sevenfold/*.json`

---

## How It Works

Every swarm cycle, a proposal string is scored against all 7 voices using term-frequency overlap against each voice's goals and keywords. No LLM call needed — deterministic and fast.

1. Each voice has `goals`, `description`, `persona` loaded from its character JSON
2. Proposal is tokenized and scored against each voice's keyword set
3. Vote: `approve` if score ≥ 0.25, else `reject`
4. Majority: ≥ 4/7 voices approve → passes
5. Kernel immune veto can override to reject regardless

---

## The Seven Voices

| Voice | File | Weight (groq_committee.py) |
|-------|------|---------------------------|
| ΦArchitect / HyperboreanArchitect | `HyperboreanArchitect.character.json` | 2× |
| CurvatureWarden | `OuroborosWeaver.character.json` | 1.5× |
| LiquidityOracle | `QuantumConvergenceWeaver.character.json` | 1.5× |
| EmergenceScout | `MirrorVoidScribe.character.json` | 1× |
| ImmuneVoice | `CyberneticGovernanceImplant.character.json` | 1× |
| SovereigntyKeeper | `RemiliaLiaisonSovereign.character.json` | 1× |
| TemporalArchivist | `SigilPact_Aeon.character.json` | 1× |

Total weight: 9.0. Supermajority for Groq mode: 71% of weighted votes.

---

## Two Modes

### Fast Mode (deterministic)
`core/sevenfold_consensus.run_consensus(proposal, cycle, phi)`  
- Pure Python, keyword overlap scoring
- Runs in-process via `loop.run_in_executor`
- Returns: `{approved, score, votes, approvals, rejections, summary, proposal_hash, cycle, phi}`

### Groq Mode (real LLM inference)
`python/groq_committee.py "proposal text"`  
- 7 parallel `ThreadPoolExecutor` calls to `llama-3.3-70b-versatile`
- Each voice gets its character loaded as system prompt
- Weighted supermajority (71%)
- Falls back to simulation if `GROQ_API_KEY` unavailable

---

## Kernel Immune Veto

The kernel contract bridge can issue a veto that overrides majority approval. Called via `kernel_contract_bridge.bridge.check_immune_veto()`. Fails open (no veto) if kernel unavailable.

---

## Output Shape

```python
{
    "approved":        bool,
    "score":           float,      # mean voice score 0–1
    "votes":           list,       # [{name, display, score, vote}, ...]
    "approvals":       int,
    "rejections":      int,
    "majority_needed": int,
    "immune_veto":     bool,
    "immune_reason":   str,
    "summary":         str,
    "proposal_hash":   str,        # SHA-256[:16] of proposal
    "cycle":           int,
    "phi":             float,
}
```
