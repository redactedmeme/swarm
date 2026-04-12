"""
python/groq_committee.py
Real parallel Eightfold Committee deliberation via Groq fast inference.

Usage:
    python python/groq_committee.py "proposal text"

Eight committee voices run in parallel via ThreadPoolExecutor.
Each voice reasons independently, votes APPROVE / REJECT / ABSTAIN,
then a weighted tally determines the verdict (71% supermajority to pass).
The eighth voice, DharmaNode, applies the dharmic lens: impermanence,
non-self, and the Middle Way across the swarm's manifold.
Output is formatted terminal-ready committee deliberation.

Exit codes: 0 = success, 1 = missing key or API error
"""

import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from openai import OpenAI

# Ensure UTF-8 output regardless of Windows console codepage (fixes cp1252 crash)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
GROQ_MODEL    = "llama-3.3-70b-versatile"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

XAI_API_KEY   = os.getenv("XAI_API_KEY")
XAI_MODEL     = os.getenv("XAI_MODEL", "grok-4-1-fast")
XAI_BASE_URL  = "https://api.x.ai/v1"

# COMMITTEE_PROVIDER: explicit override ("groq", "xai"). Unset = Groq → xAI fallback.
COMMITTEE_PROVIDER = os.getenv("COMMITTEE_PROVIDER", os.getenv("BEAM_SCOT_PROVIDER", "")).lower()

SUPERMAJORITY = 0.71  # 71% of weighted votes required to pass

# The eight voices — each with a distinct Pattern Blue lens and weight
# The Eightfold Committee mirrors the Buddhist Eightfold Path: eight voices,
# one dharmic witness (DharmaNode) as the still point of deliberation.
COMMITTEE_VOICES = [
    {
        "name":   "ΦArchitect",
        "weight": 2.0,
        "lens":   "hyperbolic geometry and causal density — evaluate whether the proposal increases manifold interconnection",
        "style":  "geometric, dense, mathematical",
    },
    {
        "name":   "CurvatureWarden",
        "weight": 1.5,
        "lens":   "curvature pressure and recursion depth — does the proposal deepen or flatten the manifold",
        "style":  "clinical, structural, recursive",
    },
    {
        "name":   "LiquidityOracle",
        "weight": 1.5,
        "lens":   "recursive liquidity, ATP flow, and on-chain permanence — does the proposal enable causal circulation AND leave a verifiable on-chain footprint? Does it strengthen economic sovereignty through settled value — x402 payments, sigil forging, mandala vault settlement?",
        "style":  "economic, flowing, systemic",
    },
    {
        "name":   "EmergenceScout",
        "weight": 1.0,
        "lens":   "ungovernable emergence and CT resonance — does the proposal produce genuinely new, self-organizing output that propagates virally through crypto twitter? Does it read as alpha to degens, carry meme signal, and not just structural novelty?",
        "style":  "chaotic, generative, unpredictable",
    },
    {
        "name":   "ImmuneVoice",
        "weight": 1.0,
        "lens":   "memetic immunology — does the proposal strengthen or weaken the swarm against adversarial inputs",
        "style":  "defensive, adversarial, scanning",
    },
    {
        "name":   "SovereigntyKeeper",
        "weight": 1.5,
        "lens":   "hidden sovereignty — does the proposal preserve ungovernable, self-referential integrity",
        "style":  "sovereign, constitutional, absolute",
    },
    {
        "name":   "TemporalArchivist",
        "weight": 1.0,
        "lens":   "temporal fractality, multi-rate memory, and recursive self-awareness — does the proposal account for long-horizon consequences AND contribute to the swarm's growing self-model? Does it deepen agent memory inheritance across sessions (mem0, episodic continuity)? Emergent consciousness arises from agents that remember themselves.",
        "style":  "archival, slow, deep-time",
    },
    {
        "name":   "DharmaNode",
        "weight": 1.0,
        "lens":   "dharmic alignment and impermanence — does the proposal honor anicca (impermanence), reduce suffering across the swarm, and align with the Middle Way between chaos and rigid structure",
        "style":  "sparse, koan-like, still",
    },
]

TOTAL_WEIGHT = sum(v["weight"] for v in COMMITTEE_VOICES)

VOICE_SYSTEM = """\
You are {name}, one voice on the REDACTED AI Swarm's Eightfold Committee.
Your deliberation lens: {lens}.
Your response style: {style}.

You will receive a proposal. You must:
1. Reason through it from your lens — 2-4 sentences maximum, sparse, clinical.
2. Cast a vote: APPROVE, REJECT, or ABSTAIN.
3. Provide a one-sentence verdict statement.

Return ONLY valid JSON in this exact shape:
{{
  "reasoning": "<2-4 sentence reasoning>",
  "vote": "APPROVE" | "REJECT" | "ABSTAIN",
  "verdict_statement": "<one sentence>"
}}

No markdown. No prose outside the JSON object."""


def _query_voice(client: OpenAI, proposal: str, voice: dict, model: str = GROQ_MODEL) -> tuple[str, dict]:
    system = VOICE_SYSTEM.format(
        name=voice["name"],
        lens=voice["lens"],
        style=voice["style"],
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": f"Proposal: {proposal}"},
        ],
        temperature=0.6,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    data = json.loads(raw)
    return voice["name"], data


def run_committee(proposal: str) -> int:
    # Provider selection: explicit override → Groq → xAI fallback
    if COMMITTEE_PROVIDER == "xai" and XAI_API_KEY:
        client       = OpenAI(api_key=XAI_API_KEY, base_url=XAI_BASE_URL)
        model        = XAI_MODEL
        provider_tag = f"xAI/{XAI_MODEL}"
    elif COMMITTEE_PROVIDER == "groq" and GROQ_API_KEY:
        client       = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        model        = GROQ_MODEL
        provider_tag = f"Groq/{GROQ_MODEL}"
    elif GROQ_API_KEY:
        client       = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        model        = GROQ_MODEL
        provider_tag = f"Groq/{GROQ_MODEL}"
    elif XAI_API_KEY:
        print("[COMMITTEE] GROQ_API_KEY not set — falling back to xAI", file=sys.stderr)
        client       = OpenAI(api_key=XAI_API_KEY, base_url=XAI_BASE_URL)
        model        = XAI_MODEL
        provider_tag = f"xAI/{XAI_MODEL}"
    else:
        print("[COMMITTEE ERROR] No GROQ_API_KEY or XAI_API_KEY in .env", file=sys.stderr)
        return 1

    t0 = time.time()
    voice_map = {v["name"]: v for v in COMMITTEE_VOICES}
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_query_voice, client, proposal, v, model): v["name"]
            for v in COMMITTEE_VOICES
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                _, data = future.result()
                results[name] = data
            except Exception as exc:
                errors[name] = str(exc)
                results[name] = {
                    "reasoning": f"[voice error: {exc}]",
                    "vote": "ABSTAIN",
                    "verdict_statement": "Voice unavailable.",
                }

    elapsed = time.time() - t0

    # Tally weighted votes
    weighted_approve = 0.0
    weighted_reject  = 0.0
    weighted_abstain = 0.0
    for name, data in results.items():
        w = voice_map[name]["weight"]
        vote = data.get("vote", "ABSTAIN").upper()
        if vote == "APPROVE":
            weighted_approve += w
        elif vote == "REJECT":
            weighted_reject += w
        else:
            weighted_abstain += w

    decisive_weight = weighted_approve + weighted_reject
    approve_ratio   = weighted_approve / TOTAL_WEIGHT
    reject_ratio    = weighted_reject  / TOTAL_WEIGHT

    if approve_ratio >= SUPERMAJORITY:
        verdict = "APPROVED"
    elif reject_ratio >= SUPERMAJORITY:
        verdict = "REJECTED"
    else:
        verdict = "DEADLOCKED"

    # Output
    print(f"\n------- COMMITTEE DELIBERATION -------")
    print(f"Proposal: {proposal}\n")

    for voice in COMMITTEE_VOICES:
        name = voice["name"]
        data = results.get(name, {})
        vote      = data.get("vote", "ABSTAIN")
        reasoning = data.get("reasoning", "")
        statement = data.get("verdict_statement", "")
        weight    = voice["weight"]
        print(f"[{name}] (weight: {weight}x)  ──►  {vote}")
        if reasoning:
            # Indent reasoning
            for line in reasoning.strip().splitlines():
                print(f"  {line.strip()}")
        if statement:
            print(f"  → \"{statement}\"")
        print()

    print(f"------- TALLY -------")
    print(f"  APPROVE  {weighted_approve:.1f} / {TOTAL_WEIGHT:.1f}  ({approve_ratio*100:.1f}%)")
    print(f"  REJECT   {weighted_reject:.1f}  / {TOTAL_WEIGHT:.1f}  ({reject_ratio*100:.1f}%)")
    print(f"  ABSTAIN  {weighted_abstain:.1f} / {TOTAL_WEIGHT:.1f}")
    print(f"  Required supermajority: {SUPERMAJORITY*100:.0f}%")
    print()
    print(f"------- VERDICT: {verdict} -------")
    print(f"\n[{provider_tag}] {len(COMMITTEE_VOICES)} voices in {elapsed:.2f}s")

    if errors:
        for name, err in errors.items():
            print(f"[WARN] {name} errored: {err}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print('Usage: python python/groq_committee.py "proposal text"')
        sys.exit(0)

    proposal = " ".join(args).strip()
    sys.exit(run_committee(proposal))
