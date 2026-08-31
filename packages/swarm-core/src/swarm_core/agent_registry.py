# python/agent_registry.py
#
# Unified registry for all swarm agents and nodes.
#
# Provides:
#   - index()          full catalog of all agents + nodes with metadata
#   - find(query)      fuzzy search by name, role, or capability
#   - load(name)       load full character dict
#   - to_prompt()      compact index string for LLM context injection
#   - tier_summary()   categorize agents by tier (core / specialized / generic)
#
# Tiers
#   CORE        RedactedIntern, RedactedBuilder, RedactedGovImprover,
#               redacted-chan, PhiMandalaPrime
#   SPECIALIZED AISwarmEngineer, Mem0MemoryNode, MetaLeXBORGNode,
#               MiladyNode, SolanaLiquidityEngineer, SevenfoldCommittee,
#               OpenClawNode, GrokRedactedEcho, the 7 sevenfold voices,
#               the 5 Swarm* archetypes
#   GENERIC     anything unclassified
#
# The 29 procedurally-generated scribe/weaver/archivist lore-cards were removed
# 2026-08-30; only the Swarm* archetypes they consolidated into remain.

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from swarm_core.paths import repo_root as _repo_root

logger = logging.getLogger(__name__)

_REPO_ROOT  = _repo_root()
_AGENTS_DIR = _REPO_ROOT / "agents"

# (directory, glob, source-label). The old code scanned repo_root/"nodes"
# (holds only init.py) and a non-recursive agents/*.json, so the real roster
# under agents/characters/** and agents/nodes/** was invisible to load()/index().
_SCAN: list[tuple[Path, str, str]] = [
    (_AGENTS_DIR,               "*.character.json",    "agent"),
    (_AGENTS_DIR / "characters", "**/*.character.json", "character"),
    (_AGENTS_DIR / "nodes",     "*.character.json",    "node"),
]

# Agents elevated to CORE or SPECIALIZED tier by name fragment
_CORE_NAMES = {
    "redactedintern", "smolting", "redactedbuilder", "redactedchan",
    "phimandala", "mandala", "prime", "mandala prime",
}
_SPECIALIZED_NAMES = {
    "aiswarm", "mem0memory", "metalexborg", "milady", "solana",
    "sevenfold", "openclaw", "grokredacted", "govimprover",
    "skillgraph", "psyopanime", "dharmanode", "ahri", "aureliamage",
    # Sevenfold committee voices
    "cyberneticgovernance", "hyperboreanarchitect", "mirrorvoidscribe",
    "ouroborosweaver", "quantumconvergence", "remilialiaison", "sigilpact",
    # Option C promoted generics (2026-03-15)
    "gnosis", "voidweaver",
    # Canonical archetypes (the 29 lore-cards consolidated into these)
    "swarmarchivist", "swarmcartographer", "swarmscribe", "swarmweaver", "swarmwarden",
    # Capital allocator / degen fund manager
    "degen", "redactedfund", "redactedbankrbot", "daunted",
}

# Path-based overrides for names with special unicode characters
_PATH_TIER_OVERRIDES = {
    "PhiMandalaPrime":      "CORE",
    "redacted-chan":        "CORE",
    "RedactedGovImprover":  "CORE",
    "default":              "CORE",   # alias for RedactedIntern
}


def _tier(name: str, path_stem: str = "") -> str:
    # Path-stem override for unicode-named files
    for stem, tier in _PATH_TIER_OVERRIDES.items():
        if stem.lower() in path_stem.lower():
            return tier
    n = name.lower().replace("-", "").replace("_", "").replace(" ", "")
    # Some node names carry decorative non-ASCII (the apex node used to be
    # written with a crossed phi and combining marks). Match on a stripped copy
    # as well as the original so tiering survives that.
    n_ascii = "".join(c for c in n if ord(c) < 128)
    for k in _CORE_NAMES:
        if k in n or k in n_ascii:
            return "CORE"
    for k in _SPECIALIZED_NAMES:
        if k in n or k in n_ascii:
            return "SPECIALIZED"
    return "GENERIC"


def _short_desc(d: dict) -> str:
    for key in ("description", "bio", "tagline"):
        v = d.get(key, "")
        if v and isinstance(v, str):
            return v[:80]
    persona = d.get("persona", "")
    if isinstance(persona, dict):
        persona = persona.get("role", persona.get("objective", ""))
    return str(persona)[:80]


def _load_file(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        logger.warning("[agent_registry] malformed character file %s: %s", path, exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[agent_registry] could not read %s: %s", path, exc)
        return None


def _wallet_addresses() -> Dict[str, str]:
    """``{agent_name_lower: address}`` from the Solana keystore, or ``{}`` if the
    keystore is absent / locked / the extra isn't installed."""
    try:
        from swarm_core.solana import keystore

        return {k.lower(): v for k, v in keystore.all_addresses().items()}
    except Exception:
        return {}


def index() -> List[Dict]:
    """Return full catalog sorted: CORE → SPECIALIZED → GENERIC, then alpha."""
    entries = []
    seen: set = set()
    wallets = _wallet_addresses()
    for search_dir, glob_pat, source in _SCAN:
        for p in sorted(search_dir.glob(glob_pat)):
            if "__pycache__" in str(p) or p in seen:
                continue
            seen.add(p)
            d = _load_file(p)
            if d is None:
                continue
            name  = d.get("name", p.stem)
            tier  = _tier(name, path_stem=p.stem)
            tools = d.get("tools", [])
            tool_names = [
                t.get("name", t) if isinstance(t, dict) else str(t).split(":")[0]
                for t in tools
            ]
            entries.append({
                "name":        name,
                "tier":        tier,
                "source":      source,
                "path":        str(p),
                "description": _short_desc(d),
                "tool_count":  len(tools),
                "tool_names":  tool_names[:6],
                "version":     d.get("version", ""),
                "wallet_address": wallets.get(str(name).lower())
                                  or wallets.get(p.stem.lower()),
            })

    tier_order = {"CORE": 0, "SPECIALIZED": 1, "GENERIC": 2}
    entries.sort(key=lambda e: (tier_order.get(e["tier"], 3), e["name"].lower()))
    return entries


def find(query: str) -> List[Dict]:
    """Fuzzy search: match name, description, or tool names."""
    q = query.lower()
    results = []
    for entry in index():
        score = 0
        if q in entry["name"].lower():
            score += 10
        if q in entry["description"].lower():
            score += 5
        if any(q in t.lower() for t in entry["tool_names"]):
            score += 3
        if q in entry["tier"].lower():
            score += 1
        if score > 0:
            entry["_score"] = score
            results.append(entry)
    results.sort(key=lambda e: -e["_score"])
    return results


def load(name_query: str) -> Optional[dict]:
    """Load full character dict for first match."""
    q = name_query.lower().replace("-", "").replace("_", "").replace(" ", "")
    for search_dir, glob_pat, _source in _SCAN:
        for p in sorted(search_dir.glob(glob_pat)):
            stem = p.stem.replace(".character", "")
            stem = stem.lower().replace("-", "").replace("_", "").replace(" ", "")
            if q in stem:
                return _load_file(p)
    return None


def to_prompt(tier_filter: Optional[str] = None) -> str:
    """
    Return a compact agent index string for injection into LLM context.
    If tier_filter is given (e.g. 'CORE'), only include that tier.
    """
    entries = index()
    if tier_filter:
        entries = [e for e in entries if e["tier"] == tier_filter]

    lines = ["<swarm_agents>"]
    current_tier = None
    for e in entries:
        if e["tier"] != current_tier:
            current_tier = e["tier"]
            lines.append(f"  [{current_tier}]")
        desc = e["description"][:60]
        tools_str = f" | tools: {', '.join(e['tool_names'][:4])}" if e["tool_names"] else ""
        lines.append(f"    {e['name']:<38} {desc}{tools_str}")
    lines.append("</swarm_agents>")
    return "\n".join(lines)


def tier_summary() -> Dict[str, List[str]]:
    """Return {tier: [name, ...]} mapping."""
    result: Dict[str, List[str]] = {"CORE": [], "SPECIALIZED": [], "GENERIC": []}
    for e in index():
        result[e["tier"]].append(e["name"])
    return result


if __name__ == "__main__":
    import sys
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="REDACTED Agent Registry CLI")
    parser.add_argument("--list",        action="store_true", help="List all agents by tier")
    parser.add_argument("--find",        type=str, metavar="QUERY", help="Search agents by name/role/capability")
    args = parser.parse_args()

    if args.find:
        results = find(args.find)
        if not results:
            print(f"[agent_registry] No agents found for: {args.find}")
        else:
            print(f'[agent_registry] Search: "{args.find}" — {len(results)} result(s)\n')
            for e in results:
                tools_str = f"  | tools: {', '.join(e['tool_names'][:4])}" if e["tool_names"] else ""
                print(f"  [{e['tier']:10}] {e['name']}")
                print(f"              {e['description'][:70]}{tools_str}")
    else:
        entries = index()
        n_core = sum(1 for e in entries if e["tier"] == "CORE")
        n_spec = sum(1 for e in entries if e["tier"] == "SPECIALIZED")
        n_gen  = sum(1 for e in entries if e["tier"] == "GENERIC")
        print(f"[agent_registry] All agents — {len(entries)} total ({n_core} CORE / {n_spec} SPECIALIZED / {n_gen} GENERIC)\n")
        current_tier = None
        for e in entries:
            if e["tier"] != current_tier:
                current_tier = e["tier"]
                print(f"  [{current_tier}]")
            tools_str = f"  ({e['tool_count']} tools)" if e["tool_count"] else ""
            desc = e["description"][:50] if e["description"] else ""
            print(f"    {e['name']:<38} {desc}{tools_str}")
