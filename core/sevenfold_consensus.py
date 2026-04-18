# core/sevenfold_consensus.py
#
# Real SevenfoldConsensus engine — loads the 7 voice character files and
# runs a weighted goal-alignment vote on any proposal string.
#
# How it works:
#   1. Each voice has a goals list and persona keywords loaded from JSON.
#   2. The proposal text is scored against each voice's goals + keywords via
#      term frequency overlap (no external LLM needed — deterministic & fast).
#   3. Votes are collected: approve if score ≥ VOICE_THRESHOLD, else reject.
#   4. A weighted majority (≥ MAJORITY_FRACTION of voices) determines outcome.
#   5. The kernel immune veto (from kernel_contract_bridge) can override to reject.
#   6. Returns a structured consensus dict suitable for _settle_economically().
#
# The scoring is intentionally lightweight — each voice's "opinion" reflects
# its goals, not a full LLM inference. This gives deterministic, fast consensus
# that can run every cycle without API cost.

import json
import re
import sys
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT     = Path(__file__).resolve().parent.parent
_SEVENFOLD_DIR = _REPO_ROOT / "agents" / "characters" / "sevenfold"
_KERNEL_DIR    = str(_REPO_ROOT / "kernel")
_PYTHON_DIR    = str(_REPO_ROOT / "python")

# Approval threshold per voice (0–1)
_VOICE_THRESHOLD   = 0.25
# Fraction of voices needed for approval (4/7 ≈ 0.57)
_MAJORITY_FRACTION = 4 / 7


def _load_voices() -> List[Dict]:
    """Load all character JSONs from the sevenfold directory."""
    voices = []
    for p in sorted(_SEVENFOLD_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            voices.append({
                "name":        d.get("name",        p.stem),
                "display":     d.get("displayName", d.get("name", p.stem)),
                "goals":       d.get("goals",       []),
                "description": d.get("description", ""),
                "persona":     d.get("persona",     ""),
                "keywords":    _extract_keywords(d),
            })
        except Exception:
            pass
    return voices


def _extract_keywords(d: Dict) -> List[str]:
    """Pull scoring keywords from a character dict."""
    kws: List[str] = []
    for goal in d.get("goals", []):
        kws += _tokenize(goal)
    kws += _tokenize(d.get("description", ""))
    kws += _tokenize(d.get("persona", ""))
    # De-dup, drop short stop-words
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "for",
            "on", "via", "all", "with", "that", "this", "are", "be", "by"}
    return list({w for w in kws if w not in stop and len(w) > 3})


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _score_voice(voice: Dict, proposal_tokens: List[str]) -> float:
    """
    Score a proposal from one voice's perspective.
    Returns 0.0–1.0: fraction of voice keywords that appear in the proposal.
    """
    kws = voice["keywords"]
    if not kws:
        return 0.5  # No keywords → neutral
    proposal_set = set(proposal_tokens)
    hits = sum(1 for k in kws if k in proposal_set)
    return min(1.0, hits / max(1, len(kws)))


def _check_immune_veto() -> Tuple[bool, str]:
    """
    Check kernel immune system for a veto signal.
    Returns (veto: bool, reason: str).
    Fails open (returns False) if kernel not available.
    """
    try:
        if _PYTHON_DIR not in sys.path:
            sys.path.insert(0, _PYTHON_DIR)
        if _KERNEL_DIR not in sys.path:
            sys.path.insert(0, _KERNEL_DIR)
        from kernel_contract_bridge import bridge
        veto   = bridge.check_immune_veto()
        reason = bridge.get_immune_veto_reason() if veto else "none"
        return veto, reason
    except Exception as e:
        return False, f"kernel_unavailable:{e}"


def run_consensus(
    proposal:       str,
    cycle:          int = 0,
    phi:            float = 0.0,
    immune_check:   bool = True,
) -> Dict:
    """
    Run a full Sevenfold Committee vote on a proposal string.

    Parameters
    ----------
    proposal      : The text of the proposal to evaluate.
    cycle         : Current swarm cycle number (for audit trail).
    phi           : Current Φ value (attached to consensus record).
    immune_check  : Whether to run the kernel immune veto gate.

    Returns
    -------
    dict with keys:
        approved        bool   — True if majority voted yes
        score           float  — Mean voice score (0–1)
        votes           list   — Per-voice {name, score, vote} records
        approvals       int    — Number of approving voices
        rejections      int    — Number of rejecting voices
        majority_needed int    — Threshold count for approval
        immune_veto     bool   — True if kernel immune system vetoed
        immune_reason   str
        summary         str    — One-line consensus summary
        proposal_hash   str    — SHA-256 of proposal (first 16 chars)
        cycle           int
        phi             float
    """
    voices         = _load_voices()
    proposal_tokens = _tokenize(proposal)
    proposal_hash  = hashlib.sha256(proposal.encode()).hexdigest()[:16]

    votes: List[Dict] = []
    for voice in voices:
        score = _score_voice(voice, proposal_tokens)
        vote  = "approve" if score >= _VOICE_THRESHOLD else "reject"
        votes.append({
            "name":    voice["name"],
            "display": voice["display"],
            "score":   round(score, 4),
            "vote":    vote,
        })

    approvals   = sum(1 for v in votes if v["vote"] == "approve")
    rejections  = len(votes) - approvals
    mean_score  = sum(v["score"] for v in votes) / max(1, len(votes))
    needed      = max(1, round(len(voices) * _MAJORITY_FRACTION))
    majority_ok = approvals >= needed

    # Kernel immune veto gate
    immune_veto, immune_reason = False, "none"
    if immune_check:
        immune_veto, immune_reason = _check_immune_veto()

    approved = majority_ok and not immune_veto

    if immune_veto:
        summary = f"VETOED by immune system ({immune_reason}) — {approvals}/{len(votes)} voices approved but kernel blocked"
    elif approved:
        summary = f"APPROVED — {approvals}/{len(votes)} voices aligned (score {mean_score:.2f}) | phi={phi:.4f}"
    else:
        summary = f"REJECTED — only {approvals}/{len(votes)} voices approved (needed {needed}) | score {mean_score:.2f}"

    return {
        "approved":        approved,
        "score":           round(mean_score, 4),
        "votes":           votes,
        "approvals":       approvals,
        "rejections":      rejections,
        "majority_needed": needed,
        "immune_veto":     immune_veto,
        "immune_reason":   immune_reason,
        "summary":         summary,
        "proposal_hash":   proposal_hash,
        "cycle":           cycle,
        "phi":             phi,
    }


def format_votes(consensus: Dict) -> str:
    """Format consensus result for terminal display."""
    lines = [
        f"[sevenfold] cycle={consensus['cycle']} phi={consensus['phi']:.4f}",
        f"  Proposal hash : {consensus['proposal_hash']}",
        f"  Result        : {'APPROVED' if consensus['approved'] else 'REJECTED'}",
        f"  Score         : {consensus['score']:.4f}  ({consensus['approvals']}/{len(consensus['votes'])} voices approve, need {consensus['majority_needed']})",
    ]
    if consensus["immune_veto"]:
        lines.append(f"  Immune veto   : {consensus['immune_reason']}")
    lines.append("  Votes:")
    for v in consensus["votes"]:
        mark = "+" if v["vote"] == "approve" else "-"
        lines.append(f"    [{mark}] {v['display']:<32} {v['score']:.3f}")
    lines.append(f"  Summary: {consensus['summary']}")
    return "\n".join(lines)
