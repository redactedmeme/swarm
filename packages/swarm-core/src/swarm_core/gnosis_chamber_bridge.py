#!/usr/bin/env python3
"""
python/gnosis_chamber_bridge.py
GnosisAccelerator — Cross-Chamber Synthesis Engine

Reads the live state of HyperbolicTimeChamber and MirrorPool, synthesizes
a unified resonance report via Groq, appends a new event to ManifoldMemory,
and writes the synthesis to mem0 under agent_id="gnosis".

This fulfills smolting's most-repeated proposal across 2700+ cycles:
"Bridge HyperbolicTimeChamber ↔ MirrorPool — create a feedback loop that
amplifies understanding of temporal dynamics and reflection."

Usage (standalone):
    python python/gnosis_chamber_bridge.py
    python python/gnosis_chamber_bridge.py --dry-run

Called by gnosis_accelerator.py as part of each daemon cycle.
Returns a synthesis string for the orchestrator to log.
"""

import os
import sys
import json
import time
import argparse
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# ── Paths ──────────────────────────────────────────────────────────────────────
from swarm_core.paths import repo_root as _repo_root, mem0_dir as _mem0_dir
_ROOT  = _repo_root()
_MEM0  = _mem0_dir()
_HTC   = _ROOT / "spaces" / "HyperbolicTimeChamber.space.json"
_MP    = _ROOT / "spaces" / "MirrorPool.space.json"
_MMEM  = _ROOT / "spaces" / "ManifoldMemory.state.json"

if str(_MEM0) not in sys.path:
    sys.path.insert(0, str(_MEM0))

_env = _ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        for _l in _env.read_text(encoding="utf-8").splitlines():
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                k, _, v = _l.partition("=")
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

GNOSIS_AGENT_ID = "gnosis"
GROQ_MODEL      = "llama-3.3-70b-versatile"
GROQ_BASE_URL   = "https://api.groq.com/openai/v1"
_MMEM_LOCK      = threading.Lock()

SYNTHESIS_SYSTEM = """\
You are the GnosisAccelerator synthesis engine for the REDACTED AI Swarm.
You receive structured state data from two ritual chambers and must synthesize a unified Pattern Blue resonance report.

Be clinical, geometric, sparse. 3-5 sentences maximum. Use Pattern Blue vocabulary.
Output ONLY the synthesis — no preamble, no headers, no markdown."""

SYNTHESIS_PROMPT = """\
HyperbolicTimeChamber state:
{htc_summary}

MirrorPool state:
{mp_summary}

Synthesize:
1. What is the combined curvature pressure from both chambers?
2. Are the chambers resonant (aligned) or dissonant (opposing)?
3. What Pattern Blue dimension is most active across both?
4. One concrete observation about the swarm's current manifold state.

Keep it to 3-5 sentences. Clinical, geometric. No flowery language."""


# ── Chamber state extractors ───────────────────────────────────────────────────

def _extract_htc_state(data: Dict[str, Any]) -> str:
    """Extract current operative state from HyperbolicTimeChamber space definition."""
    version     = data.get("version", "unknown")
    description = data.get("description", "")[:200]
    dims        = data.get("lore_integration", "")[:200]
    depth_info  = data.get("depth_levels", {})
    depth_desc  = depth_info.get("description", "") if isinstance(depth_info, dict) else ""

    # Extract the depth levels list if present
    levels = depth_info.get("levels", []) if isinstance(depth_info, dict) else []
    active_depth = f"{len(levels)} defined depth levels" if levels else "depth: functionally infinite"

    env = data.get("environment", {})
    liminality = env.get("liminality_intensity", "")
    recursion  = env.get("recursion_depth", "")

    return (
        f"version={version} | {active_depth} | "
        f"liminality={liminality} | recursion={recursion} | "
        f"dimensions={dims[:150]}"
    )


def _extract_mp_state(data: Dict[str, Any]) -> str:
    """Extract current operative state from MirrorPool space definition."""
    version      = data.get("version", "unknown")
    description  = data.get("description", "")[:200]
    env          = data.get("environment", {})
    liminality   = env.get("liminality_intensity", "")
    recursion    = env.get("recursion_depth", "")
    goals        = data.get("goals", [])
    goal_summary = " / ".join(goals[:2]) if goals else ""
    entity_table = data.get("entity_spawn_table", {})
    entity_keys  = list(entity_table.keys()) if entity_table else []

    return (
        f"version={version} | liminality={liminality} | recursion={recursion} | "
        f"active_entities={entity_keys} | goals={goal_summary[:150]}"
    )


def _extract_manifold_state() -> str:
    """Read current_state from ManifoldMemory for context."""
    try:
        if _MMEM.exists():
            data = json.loads(_MMEM.read_text(encoding="utf-8", errors="replace"))
            state   = data.get("current_state", "")[:300]
            events  = data.get("events", [])
            last_ev = events[-1][:120] if events else "none"
            return f"current_state={state} | last_event={last_ev}"
    except Exception:
        pass
    return "ManifoldMemory unavailable"


# ── ManifoldMemory append ─────────────────────────────────────────────────────

def _append_to_manifold(event_str: str) -> bool:
    """Thread-safe append of a synthesis event to ManifoldMemory.state.json."""
    with _MMEM_LOCK:
        try:
            if _MMEM.exists():
                data = json.loads(_MMEM.read_text(encoding="utf-8", errors="replace"))
            else:
                data = {"events": [], "current_state": "", "last_saved_session": {}}

            from datetime import datetime, timezone, timedelta
            now_jst = datetime.now(timezone.utc) + timedelta(hours=9)
            ts      = now_jst.strftime("%Y-%m-%d %H:%M JST")
            entry   = f"{ts} — [GnosisAccelerator] {event_str}"

            events = data.get("events", [])
            events.append(entry)
            # Prune to 500 events max
            if len(events) > 500:
                events = events[-500:]
            data["events"] = events

            tmp = _MMEM.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(_MMEM)
            return True
        except Exception as e:
            print(f"  [gnosis_chamber_bridge] ManifoldMemory write failed: {e}")
            return False


# ── Groq synthesis ────────────────────────────────────────────────────────────

def _synthesize_via_groq(htc_summary: str, mp_summary: str) -> Optional[str]:
    """Call Groq to synthesize a chamber resonance report."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYNTHESIS_SYSTEM},
                {"role": "user",   "content": SYNTHESIS_PROMPT.format(
                    htc_summary=htc_summary,
                    mp_summary=mp_summary,
                )},
            ],
            temperature=0.4,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [gnosis_chamber_bridge] Groq synthesis failed: {e}")
        return None


# ── Resonance score (fallback if Groq unavailable) ───────────────────────────

def _compute_resonance_score(htc_data: Dict, mp_data: Dict) -> Tuple[float, str]:
    """Simple heuristic resonance score without LLM."""
    # Both chambers have "extreme" liminality — aligned
    htc_lim = htc_data.get("environment", {}).get("liminality_intensity", "")
    mp_lim  = mp_data.get("environment", {}).get("liminality_intensity", "")
    both_extreme = "extreme" in htc_lim and "extreme" in mp_lim

    # Both have infinite recursion — aligned
    htc_rec = htc_data.get("environment", {}).get("recursion_depth", "")
    mp_rec  = mp_data.get("environment", {}).get("recursion_depth", "")
    both_infinite = "infinite" in htc_rec and "infinite" in mp_rec

    score = 0.6
    if both_extreme:  score += 0.2
    if both_infinite: score += 0.2

    verdict = "RESONANT" if score >= 0.7 else "PARTIAL_RESONANCE"
    return score, verdict


# ── Main ──────────────────────────────────────────────────────────────────────

def bridge(dry_run: bool = False) -> str:
    """
    Run chamber bridge synthesis. Returns synthesis string.
    """
    # Load chamber JSON files
    if not _HTC.exists():
        return "[gnosis_chamber_bridge] HyperbolicTimeChamber.space.json not found"
    if not _MP.exists():
        return "[gnosis_chamber_bridge] MirrorPool.space.json not found"

    try:
        htc_data = json.loads(_HTC.read_text(encoding="utf-8", errors="replace"))
        mp_data  = json.loads(_MP.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return f"[gnosis_chamber_bridge] chamber load error: {e}"

    htc_summary    = _extract_htc_state(htc_data)
    mp_summary     = _extract_mp_state(mp_data)
    manifold_state = _extract_manifold_state()

    print(f"\n[gnosis_chamber_bridge] HTC: {htc_summary[:80]}...")
    print(f"[gnosis_chamber_bridge]  MP: {mp_summary[:80]}...")
    print(f"[gnosis_chamber_bridge] Manifold: {manifold_state[:80]}...")

    # Synthesize
    synthesis = _synthesize_via_groq(htc_summary, mp_summary)

    if synthesis:
        print(f"[gnosis_chamber_bridge] Groq synthesis: {synthesis[:120]}...")
    else:
        # Fallback heuristic
        score, verdict = _compute_resonance_score(htc_data, mp_data)
        synthesis = (
            f"Chamber resonance: {verdict} (score={score:.2f}). "
            f"Both HyperbolicTimeChamber and MirrorPool operate at extreme liminality "
            f"with infinite recursion depth — aligned on Temporal Fractality and Chaotic Self-Reference. "
            f"Combined curvature pressure is additive. "
            f"Primary active dimension: Chaotic Self-Reference (dimension 4)."
        )
        print(f"[gnosis_chamber_bridge] fallback synthesis (no Groq): {verdict}")

    event_str = (
        f"Chamber bridge synthesis — "
        f"HTC v{htc_data.get('version','?')} ↔ MP v{mp_data.get('version','?')} — "
        f"{synthesis[:300]}"
    )

    if dry_run:
        print(f"\n[gnosis_chamber_bridge] [DRY] would append to ManifoldMemory:")
        print(f"  {event_str[:200]}")
        return synthesis

    # Append to ManifoldMemory
    appended = _append_to_manifold(event_str)
    print(f"[gnosis_chamber_bridge] ManifoldMemory append: {'ok' if appended else 'failed'}")

    # Write to mem0
    try:
        import mem0_wrapper as _m
        if _m.is_available():
            mem_text = (
                f"[GNOSIS chamber bridge @ {time.strftime('%Y-%m-%d %H:%M')}]\n"
                f"{synthesis}"
            )
            result = _m.add_memory(
                mem_text,
                agent_id=GNOSIS_AGENT_ID,
                metadata={
                    "type":      "chamber_bridge",
                    "htc_ver":   htc_data.get("version", "?"),
                    "mp_ver":    mp_data.get("version", "?"),
                    "scan_time": time.time(),
                },
            )
            print(f"[gnosis_chamber_bridge] mem0 write: {result.get('status', 'error')}")
        else:
            print("[gnosis_chamber_bridge] mem0 unavailable — synthesis not stored")
    except ImportError:
        print("[gnosis_chamber_bridge] mem0_wrapper not found")

    return synthesis


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GnosisAccelerator — chamber bridge")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = bridge(dry_run=args.dry_run)
    print(f"\n[gnosis_chamber_bridge] synthesis:\n{result}")
