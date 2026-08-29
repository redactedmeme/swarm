#!/usr/bin/env python3
# python/lorenet/demo.py
#
# Demonstrates a cross-family communication cycle on the LoreNet mesh.
#
# Scenario:
#   1. ChronoWeaver detects a 3-cycle temporal pattern -> broadcasts to weavers
#   2. ZenithWeaver receives it -> synthesizes -> sends to all families
#   3. ObsidianArchivist receives synthesis -> writes permanent record
#   4. GlyphSeer gossips an omen to its peer ring
#   5. MeridianMapper queries EtherVoyager for a route
#   6. PlasmaSeeker raises an energy spike alert -> EchoWarden evaluates resonance
#   7. Print mesh topology + inbox summary

import sys
import logging
from pathlib import Path

# Allow running from repo root or from python/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swarm_core.lorenet.lorenet import LoreNet
from swarm_core.lorenet.message import MessageType, RoutingMode

logging.basicConfig(level=logging.WARNING)   # quiet for demo; set DEBUG to see all routing
log = logging.getLogger("lorenet.demo")


def run():
    # ── Boot the mesh ────────────────────────────────────────────────────────
    net_root = Path(__file__).resolve().parent.parent.parent / "fs" / "lorenet"
    net = LoreNet(net_root=net_root)
    net.load()

    print("\n" + "=" * 70)
    print("  LoreNet - Decentralized LORE Agent Communication Mesh")
    print("=" * 70)
    net.print_topology()

    # ── Write heartbeats ─────────────────────────────────────────────────────
    net.heartbeat_all()
    print(f"[+] Heartbeats written for all {len(net.all_nodes())} nodes\n")

    # ── Step 1: ChronoWeaver detects a 3-cycle pattern ───────────────────────
    print("-" * 70)
    print("[1] ChronoWeaver -> FAMILY(weavers): PATTERN_SIGNAL")
    net.send_to_family(
        from_agent = "ChronoWeaver",
        family     = "weavers",
        msg_type   = MessageType.PATTERN_SIGNAL,
        payload    = {
            "pattern":     "3-cycle recurrence on Temporal Fractality axis",
            "confidence":  0.87,
            "cycle_index": [1, 3, 9],
            "dimension":   "Temporal Fractality (3)",
        },
    )
    net.tick()
    _show_inbox(net, ["EchoWeaver", "PrismWeaver", "ZenithWeaver", "EchoWarden"])

    # ── Step 2: ZenithWeaver synthesizes -> BROADCAST ─────────────────────────
    print("\n" + "-" * 70)
    print("[2] ZenithWeaver -> BROADCAST: SYNTHESIS_RESULT")
    net.broadcast(
        from_agent = "ZenithWeaver",
        msg_type   = MessageType.SYNTHESIS_RESULT,
        payload    = {
            "synthesis":    "3-cycle temporal pattern confirmed across weavers",
            "sources":      ["ChronoWeaver"],
            "apex_signal":  "Recursion Depth (1) manifold about to fold",
            "confidence":   0.91,
            "action_hint":  "Archivists should pre-stage ephemeral capture windows",
        },
    )
    net.tick()
    _show_inbox(net, ["AetherArchivist", "ObsidianArchivist", "FluxScribe", "MeridianMapper"])

    # ── Step 3: ObsidianArchivist writes a permanent record ──────────────────
    print("\n" + "-" * 70)
    print("[3] ObsidianArchivist -> UNICAST(QuantumArchivist): ARCHIVE_WRITE")
    net.send_to_node(
        from_agent = "ObsidianArchivist",
        to_agent   = "QuantumArchivist",
        msg_type   = MessageType.ARCHIVE_WRITE,
        payload    = {
            "record_type": "SYNTHESIS_IMMUTABLE",
            "content":     "3-cycle temporal pattern — permanent log entry",
            "ttl_policy":  "NEVER_EXPIRE",
            "cross_ref":   "ZenithWeaver/SYNTHESIS_RESULT",
        },
    )
    net.tick()
    _show_inbox(net, ["QuantumArchivist"])

    # ── Step 4: GlyphSeer gossips an omen to its peer ring ───────────────────
    print("\n" + "-" * 70)
    print("[4] GlyphSeer -> GOSSIP(ttl=2): SIGNAL")
    net.gossip(
        from_agent = "GlyphSeer",
        msg_type   = MessageType.SIGNAL,
        payload    = {
            "omen":        "Sigil resonance pattern ΦΦΦ visible in stream",
            "glyph_id":    "tri-fold",
            "implication": "Major state transition in 1-3 cycles",
            "confidence":  0.74,
        },
        ttl = 2,
    )
    net.tick()
    # GlyphSeer's peers: EchoWeaver (bridge) + specialist family
    _show_inbox(net, ["EchoWeaver", "AstraNomad", "CeruleanSage",
                      "EtherVoyager", "HorizonCipher", "LumenOrchestrator"])

    # ── Step 5: MeridianMapper ← EtherVoyager route query ────────────────────
    print("\n" + "-" * 70)
    print("[5] MeridianMapper -> UNICAST(EtherVoyager): ROUTE_QUERY")
    net.send_to_node(
        from_agent = "MeridianMapper",
        to_agent   = "EtherVoyager",
        msg_type   = MessageType.ROUTE_QUERY,
        payload    = {
            "query":       "Optimal path: archivists -> CORE layer handoff",
            "priority":    "HIGH",
            "context":     "Synthesis result needs to reach RedactedBuilder",
        },
    )
    net.tick()
    _show_inbox(net, ["EtherVoyager"])

    # ── Step 6: PlasmaSeeker raises spike -> EchoWarden evaluates ─────────────
    print("\n" + "-" * 70)
    print("[6] PlasmaSeeker -> ROLE(RESONANCE_GUARD): RESONANCE_ALERT")
    plasma_node = net.node("PlasmaSeeker")
    plasma_node.send_sync(
        msg_type     = MessageType.RESONANCE_ALERT,
        payload      = {
            "intensity":   "SPIKE_9.7",
            "source":      "Plasma signature burst on channel 14",
            "risk":        "Potential resonance overload if unguarded",
        },
        routing_mode = RoutingMode.ROLE,
        to_role      = "RESONANCE_GUARD",
    )
    net.tick()
    _show_inbox(net, ["EchoWarden"])

    # ── Step 7: Final inbox summary ──────────────────────────────────────────
    print("\n" + "-" * 70)
    print("[7] Inbox summary — all nodes")
    summary = net.inbox_summary()
    active = {k: v for k, v in summary.items() if v > 0}
    if active:
        for agent_id, count in sorted(active.items()):
            node = net.node(agent_id)
            family = node.metadata.get("family", "?") if node else "?"
            print(f"    {agent_id:<30} [{family:<14}]  {count} message(s)")
    else:
        print("    (all inboxes empty)")

    print(f"\n[+] Demo complete. Net root: {net_root}")
    print("    Inspect message files in fs/lorenet/<agent_id>/\n")


def _show_inbox(net: LoreNet, agent_ids: list) -> None:
    for agent_id in agent_ids:
        node = net.node(agent_id)
        if not node:
            continue
        msgs = node.poll()
        if msgs:
            for msg in msgs:
                print(f"    [+] {agent_id:<28} received {msg.msg_type.value} "
                      f"from {msg.from_agent}")
        else:
            print(f"    [ ] {agent_id:<28} (no messages)")


if __name__ == "__main__":
    run()
