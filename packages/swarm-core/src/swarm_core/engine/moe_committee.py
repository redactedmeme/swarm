# core/moe_committee.py
#
# MoE Committee (mixture-of-experts) — the swarm's single deliberation body.
#
# Canonical replacement for three drifted committee implementations that used
# to coexist (8-voice groq_committee.py, 7-voice deterministic
# sevenfold_consensus.py, 7-voice generic-LLM committee_engine.py). Reconciled
# to ONE body: the 7 voices defined in agents/characters/sevenfold/, with a
# 71% weighted supermajority threshold on every deliberation path.
#
# Two modes, same voices, same threshold:
#   - deterministic  : keyword/goal-overlap scoring, no LLM call, fast & free.
#   - llm            : each voice reasons via a live LLM call (multi-provider),
#                       run in parallel via ThreadPoolExecutor.
#
# `core/sevenfold_consensus.py`, `python/committee_engine.py`, and
# `python/groq_committee.py` are now thin back-compat shims over this module —
# see those files for the call sites they preserve.

import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

from swarm_core.paths import repo_root as _repo_root
_REPO_ROOT     = _repo_root()
_SEVENFOLD_DIR = _REPO_ROOT / "agents" / "characters" / "sevenfold"

# Single reconciled threshold for every mode/path.
SUPERMAJORITY = 0.71


# ── Voice loading (shared by both modes) ──────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _extract_keywords(d: Dict) -> List[str]:
    kws: List[str] = []
    for goal in d.get("goals", []):
        kws += _tokenize(goal)
    kws += _tokenize(d.get("description", ""))
    kws += _tokenize(d.get("persona", ""))
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "for",
            "on", "via", "all", "with", "that", "this", "are", "be", "by"}
    return list({w for w in kws if w not in stop and len(w) > 3})


def load_voices() -> List[Dict]:
    """Load the 7 canonical committee voices from agents/characters/sevenfold/."""
    voices = []
    for p in sorted(_SEVENFOLD_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        voices.append({
            "name":        d.get("name", p.stem),
            "display":     d.get("displayName", d.get("name", p.stem)),
            "role":        d.get("role", ""),
            "goals":       d.get("goals", []),
            "description": d.get("description", ""),
            "persona":     d.get("persona", ""),
            "lens":        d.get("description", "") or d.get("persona", "") or "general alignment",
            "weight":      float(d.get("default_weight", 1.0)),
            "keywords":    _extract_keywords(d),
        })
    return voices


VOICES       = load_voices()
TOTAL_WEIGHT = sum(v["weight"] for v in VOICES) or 1.0


# ── Deterministic mode (fast, free, no LLM) ────────────────────────────────────

_VOICE_THRESHOLD = 0.25  # per-voice approve threshold (0-1 keyword-overlap score)


def _score_voice(voice: Dict, proposal_tokens: List[str]) -> float:
    kws = voice["keywords"]
    if not kws:
        return 0.5
    proposal_set = set(proposal_tokens)
    hits = sum(1 for k in kws if k in proposal_set)
    return min(1.0, hits / max(1, len(kws)))


def _check_immune_veto() -> Tuple[bool, str]:
    """Kernel immune veto gate. Fails open if the kernel isn't available."""
    try:
        from swarm_core.kernel_contract_bridge import bridge
        veto   = bridge.check_immune_veto()
        reason = bridge.get_immune_veto_reason() if veto else "none"
        return veto, reason
    except Exception as e:
        return False, f"kernel_unavailable:{e}"


def run_consensus(
    proposal:     str,
    cycle:        int = 0,
    phi:          float = 0.0,
    immune_check: bool = True,
) -> Dict:
    """
    Deterministic (no-LLM) weighted vote across the 7 committee voices.
    Threshold: SUPERMAJORITY (71%) of total voice weight, weighted by each
    voice's approve-scaled score.
    """
    voices          = VOICES
    proposal_tokens = _tokenize(proposal)
    proposal_hash   = hashlib.sha256(proposal.encode()).hexdigest()[:16]

    votes: List[Dict] = []
    weighted_approve = 0.0
    for voice in voices:
        score = _score_voice(voice, proposal_tokens)
        vote  = "approve" if score >= _VOICE_THRESHOLD else "reject"
        if vote == "approve":
            weighted_approve += voice["weight"]
        votes.append({
            "name":    voice["name"],
            "display": voice["display"],
            "score":   round(score, 4),
            "vote":    vote,
        })

    approvals    = sum(1 for v in votes if v["vote"] == "approve")
    rejections   = len(votes) - approvals
    mean_score   = sum(v["score"] for v in votes) / max(1, len(votes))
    approve_ratio = weighted_approve / TOTAL_WEIGHT
    majority_ok  = approve_ratio >= SUPERMAJORITY

    immune_veto, immune_reason = (False, "none")
    if immune_check:
        immune_veto, immune_reason = _check_immune_veto()

    approved = majority_ok and not immune_veto

    if immune_veto:
        summary = f"VETOED by immune system ({immune_reason}) — {approve_ratio:.0%} weighted approval but kernel blocked"
    elif approved:
        summary = f"APPROVED — {approve_ratio:.0%} weighted approval (score {mean_score:.2f}) | phi={phi:.4f}"
    else:
        summary = f"REJECTED — only {approve_ratio:.0%} weighted approval (needed {SUPERMAJORITY:.0%}) | score {mean_score:.2f}"

    return {
        "approved":        approved,
        "score":           round(mean_score, 4),
        "votes":           votes,
        "approvals":       approvals,
        "rejections":      rejections,
        "approve_ratio":   round(approve_ratio, 4),
        "majority_needed": SUPERMAJORITY,
        "immune_veto":     immune_veto,
        "immune_reason":   immune_reason,
        "summary":         summary,
        "proposal_hash":   proposal_hash,
        "cycle":           cycle,
        "phi":             phi,
    }


def format_votes(consensus: Dict) -> str:
    """Format a deterministic consensus result for terminal display."""
    lines = [
        f"[moe_committee] cycle={consensus['cycle']} phi={consensus['phi']:.4f}",
        f"  Proposal hash : {consensus['proposal_hash']}",
        f"  Result        : {'APPROVED' if consensus['approved'] else 'REJECTED'}",
        f"  Score         : {consensus['score']:.4f}  ({consensus['approve_ratio']:.0%} weighted approval, need {consensus['majority_needed']:.0%})",
    ]
    if consensus["immune_veto"]:
        lines.append(f"  Immune veto   : {consensus['immune_reason']}")
    lines.append("  Votes:")
    for v in consensus["votes"]:
        mark = "+" if v["vote"] == "approve" else "-"
        lines.append(f"    [{mark}] {v['display']:<32} {v['score']:.3f}")
    lines.append(f"  Summary: {consensus['summary']}")
    return "\n".join(lines)


# ── LLM mode (live deliberation, multi-provider) ───────────────────────────────

VOICE_SYSTEM = """\
You are {name}, one voice on the REDACTED AI Swarm's MoE Committee.
Your deliberation lens: {lens}.

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


def _llm_json(system: str, user: str) -> dict:
    """
    Single-turn JSON-mode LLM call via Groq (preferred, fast) → xAI fallback.
    Raises on failure; caller handles as an ABSTAIN.
    """
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(str(_REPO_ROOT / ".env"))

    groq_key = os.getenv("GROQ_API_KEY")
    xai_key  = os.getenv("XAI_API_KEY")
    provider = os.getenv("COMMITTEE_PROVIDER", os.getenv("BEAM_SCOT_PROVIDER", "")).lower()

    if provider == "xai" and xai_key:
        client, model = OpenAI(api_key=xai_key, base_url="https://api.x.ai/v1"), os.getenv("XAI_MODEL", "grok-4-1-fast")
    elif groq_key:
        client, model = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1"), "llama-3.3-70b-versatile"
    elif xai_key:
        client, model = OpenAI(api_key=xai_key, base_url="https://api.x.ai/v1"), os.getenv("XAI_MODEL", "grok-4-1-fast")
    else:
        raise RuntimeError("No GROQ_API_KEY or XAI_API_KEY in .env")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.6,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def _deliberate_voice(voice: Dict, proposal: str) -> Dict:
    system = VOICE_SYSTEM.format(name=voice["name"], lens=voice["lens"])
    try:
        data = _llm_json(system, f"Proposal: {proposal}")
    except Exception as e:
        data = {
            "reasoning": f"[voice error: {e}]",
            "vote": "ABSTAIN",
            "verdict_statement": "Voice unavailable.",
        }
    return {**voice, **data}


def deliberate(proposal: str) -> str:
    """
    Run a full live LLM deliberation across the 7 committee voices in
    parallel. Returns a formatted terminal-style output string. Threshold:
    SUPERMAJORITY (71%) weighted approval.
    """
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(VOICES) or 1) as pool:
        futures = {pool.submit(_deliberate_voice, v, proposal): v["name"] for v in VOICES}
        results_by_name = {futures[f]: f.result() for f in as_completed(futures)}
    elapsed = time.time() - t0

    lines = [
        "------- MOE COMMITTEE DELIBERATION -------",
        f"Proposal: {proposal}",
        "",
    ]

    weighted_approve = weighted_reject = weighted_abstain = 0.0
    for voice in VOICES:
        r = results_by_name[voice["name"]]
        vote = r.get("vote", "ABSTAIN").upper()
        w = voice["weight"]
        if vote == "APPROVE":
            weighted_approve += w
        elif vote == "REJECT":
            weighted_reject += w
        else:
            weighted_abstain += w

        lines.append(f"[{voice['name']}] (weight: {w}x)  ──►  {vote}")
        reasoning = r.get("reasoning", "")
        if reasoning:
            for line in reasoning.strip().splitlines():
                lines.append(f"  {line.strip()}")
        statement = r.get("verdict_statement", "")
        if statement:
            lines.append(f'  → "{statement}"')
        lines.append("")

    approve_ratio = weighted_approve / TOTAL_WEIGHT
    reject_ratio  = weighted_reject / TOTAL_WEIGHT
    if approve_ratio >= SUPERMAJORITY:
        verdict = "APPROVED"
    elif reject_ratio >= SUPERMAJORITY:
        verdict = "REJECTED"
    else:
        verdict = "DEADLOCKED"

    lines += [
        "------- TALLY -------",
        f"  APPROVE  {weighted_approve:.1f} / {TOTAL_WEIGHT:.1f}  ({approve_ratio*100:.1f}%)",
        f"  REJECT   {weighted_reject:.1f}  / {TOTAL_WEIGHT:.1f}  ({reject_ratio*100:.1f}%)",
        f"  ABSTAIN  {weighted_abstain:.1f} / {TOTAL_WEIGHT:.1f}",
        f"  Required supermajority: {SUPERMAJORITY*100:.0f}%",
        "",
        f"------- VERDICT: {verdict} -------",
        f"\n{len(VOICES)} voices in {elapsed:.2f}s",
    ]
    return "\n".join(lines)


def run_committee(proposal: str) -> int:
    """CLI entrypoint: prints the LLM deliberation, returns a process exit code."""
    try:
        print(deliberate(proposal))
        return 0
    except Exception as e:
        print(f"[COMMITTEE ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if not args:
        print('Usage: python core/moe_committee.py "proposal text"')
        sys.exit(0)
    sys.exit(run_committee(" ".join(args).strip()))
