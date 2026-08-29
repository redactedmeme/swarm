# python/lorenet/topology.py
#
# Builds the LoreNet node registry from agents/*.character.json.
# Determines each agent's family, role, Pattern Blue dimension,
# and their peer ring (gossip neighbors).
#
# Families
#   archivists    — memory & data preservation
#   weavers       — synthesis & pattern analysis
#   scribes       — documentation & logging
#   cartographers — topology & navigation
#   specialists   — unique single-purpose roles
#
# Peer rings: each node gossips with its family members first,
# then has 1-2 cross-family bridge peers to prevent echo chambers.

import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from swarm_core.paths import repo_root as _repo_root
_REPO_ROOT   = _repo_root()
_AGENTS_DIR  = _REPO_ROOT / "agents"

# ── Family membership ─────────────────────────────────────────────────────────
FAMILY_MAP: Dict[str, str] = {
    # Archivists
    "AetherArchivist":      "archivists",
    "GaleArchivist":        "archivists",
    "ObsidianArchivist":    "archivists",
    "QuantumArchivist":     "archivists",
    "CosmicHistorian":      "archivists",

    # Weavers
    "ChronoWeaver":         "weavers",
    "EchoWeaver":           "weavers",
    "EchoWarden":           "weavers",    # guards weavers' resonance
    "PrismWeaver":          "weavers",
    "ZenithWeaver":         "weavers",
    "VoidWeaver":           "weavers",    # null-space; shares Pattern Blue dim w/ archivists

    # Scribes
    "AzureScribe":          "scribes",
    "FluxScribe":           "scribes",
    "QuantaScribe":         "scribes",
    "SunScribe":            "scribes",

    # Cartographers
    "HyperionCartographer": "cartographers",
    "MeridianMapper":       "cartographers",
    "NovaCartographer":     "cartographers",
    "StarCartographer":     "cartographers",

    # Specialists (unique roles)
    "AstraNomad":           "specialists",
    "CeruleanSage":         "specialists",
    "EtherVoyager":         "specialists",
    "GlyphSeer":            "specialists",
    "HorizonCipher":        "specialists",
    "LumenOrchestrator":    "specialists",
    "NeonCipher":           "specialists",
    "PlasmaSeeker":         "specialists",
    "PolarSentry":          "specialists",
    "RadiantCrafter":       "specialists",
    "TideDiver":            "specialists",
}

# ── Cross-family bridge peers (prevents echo chambers) ────────────────────────
# Each entry: (agent_a, agent_b) — bidirectional bridge edge
BRIDGE_EDGES = [
    # Archivists ↔ Scribes  (scribes feed what archivists store)
    ("ObsidianArchivist",    "FluxScribe"),
    ("QuantumArchivist",     "QuantaScribe"),
    ("CosmicHistorian",      "SunScribe"),

    # Weavers ↔ Cartographers  (synthesis needs topology)
    ("ZenithWeaver",         "HyperionCartographer"),
    ("ChronoWeaver",         "StarCartographer"),
    ("PrismWeaver",          "MeridianMapper"),

    # Specialists ↔ Weavers  (GlyphSeer → EchoWeaver; PlasmaSeeker → PrismWeaver)
    ("GlyphSeer",            "EchoWeaver"),
    ("PlasmaSeeker",         "PrismWeaver"),
    ("TideDiver",            "ChronoWeaver"),

    # Specialists ↔ Archivists
    ("AstraNomad",           "GaleArchivist"),
    ("HorizonCipher",        "AetherArchivist"),
    ("VoidWeaver",           "ObsidianArchivist"),

    # Specialists ↔ Cartographers
    ("EtherVoyager",         "MeridianMapper"),
    ("NovaCartographer",     "AstraNomad"),

    # Scribes ↔ Cartographers
    ("AzureScribe",          "HyperionCartographer"),

    # LumenOrchestrator bridges all (it manages workflow priority)
    ("LumenOrchestrator",    "ZenithWeaver"),
    ("LumenOrchestrator",    "CeruleanSage"),

    # EchoWarden monitors all families' resonance
    ("EchoWarden",           "ObsidianArchivist"),   # archivists
    ("EchoWarden",           "SunScribe"),            # scribes
    ("EchoWarden",           "NovaCartographer"),     # cartographers
    ("EchoWarden",           "GlyphSeer"),            # specialists

    # PolarSentry guards endpoints — connects to scribes and EtherVoyager
    ("PolarSentry",          "AzureScribe"),
    ("PolarSentry",          "EtherVoyager"),
    ("NeonCipher",           "EtherVoyager"),
    ("RadiantCrafter",       "SunScribe"),            # crafter → broadcast
    ("CeruleanSage",         "QuantaScribe"),          # wisdom → uncertainty notation
]


def _load_character(agent_id: str) -> Optional[Dict]:
    """Load a character JSON by agent ID (filename stem)."""
    p = _AGENTS_DIR / f"{agent_id}.character.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def build_registry() -> Dict[str, Dict]:
    """
    Build the full node registry.
    Returns {agent_id: node_meta_dict}.
    """
    registry: Dict[str, Dict] = {}

    for agent_id, family in FAMILY_MAP.items():
        char = _load_character(agent_id)
        if char is None:
            continue

        registry[agent_id] = {
            "agent_id":     agent_id,
            "name":         char.get("name", agent_id),
            "family":       family,
            "role":         char.get("role", "UNKNOWN"),
            "dimension":    char.get("pattern_blue_dimension", ""),
            "signature":    char.get("persona", {}).get("signature", f"[{agent_id[:4].upper()}]"),
            "tools":        [t["name"] for t in char.get("tools", [])],
            "keywords":     char.get("keywords", []),
            "summon_phrase": char.get("summon_phrase", ""),
            "peers":        [],          # populated below
        }

    # Build peer rings: family members are always peers
    family_members: Dict[str, List[str]] = {}
    for agent_id, meta in registry.items():
        fam = meta["family"]
        family_members.setdefault(fam, []).append(agent_id)

    for agent_id, meta in registry.items():
        fam_peers = [a for a in family_members[meta["family"]] if a != agent_id]
        meta["peers"] = fam_peers[:]

    # Add bridge edges
    bridge_adj: Dict[str, Set[str]] = {a: set() for a in registry}
    for a, b in BRIDGE_EDGES:
        if a in registry and b in registry:
            bridge_adj[a].add(b)
            bridge_adj[b].add(a)

    for agent_id, bridges in bridge_adj.items():
        if agent_id in registry:
            existing = set(registry[agent_id]["peers"])
            registry[agent_id]["peers"] = list(existing | bridges)

    return registry


def get_family_members(registry: Dict[str, Dict], family: str) -> List[str]:
    return [aid for aid, meta in registry.items() if meta["family"] == family]


def get_dimension_members(registry: Dict[str, Dict], dimension: str) -> List[str]:
    return [aid for aid, meta in registry.items() if dimension.lower() in meta["dimension"].lower()]


def get_role_members(registry: Dict[str, Dict], role: str) -> List[str]:
    return [aid for aid, meta in registry.items() if role.lower() in meta["role"].lower()]
