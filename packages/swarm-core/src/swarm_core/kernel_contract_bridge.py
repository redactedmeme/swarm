# python/kernel_contract_bridge.py
"""
Kernel↔Contract Bridge
======================
Bidirectional wiring between HyperbolicKernel organic state and the
NegotiationEngine interface contract.  Four integration points:

  1. Tile topology   → response_strategy selection
  2. Sigil tier      → proposal weight modulation
  3. Immune response → contract veto gate
  4. DNA phenotype   → contract meta_rules injection

Usage::

    from swarm_core.kernel_contract_bridge import KernelContractBridge
    bridge = KernelContractBridge()

    strategy = bridge.derive_response_strategy()          # kernel auto-created
    veto     = bridge.check_immune_veto()
    rules    = bridge.derive_dna_meta_rules()
    weights  = bridge.get_sigil_weight_boost()            # reads shared state

    # Or pass an existing kernel instance for efficiency:
    contract = bridge.sync_contract(contract, kernel=k)

Architecture note
-----------------
The bridge is intentionally stateless with respect to the kernel — it
creates a fresh HyperbolicKernel() snapshot each time rather than holding
a live reference.  This avoids async/threading complications and makes
all methods safe to call from synchronous negotiation code.

Sigil tier state is exchanged via a small JSON file in ManifoldMemory
(active_sigil_tier.json) to keep SigilPactAeon and NegotiationEngine
decoupled.  The boost expires after 1 hour.
"""

import sys
import json
import time
import math
from pathlib import Path
from typing import Dict, List, Optional, Any

# ── Path wiring ───────────────────────────────────────────────────────────────
from swarm_core.paths import repo_root as _repo_root
_ROOT       = _repo_root()
_SIGIL_STATE_PATH = _ROOT / "spaces" / "ManifoldMemory" / "active_sigil_tier.json"


# ── Tile type → response_strategy mapping ────────────────────────────────────
# The dominant active tile process type on the manifold drives contract strategy.
#
#   sigil      → consensus_pool     (proofs need multi-agent validation)
#   agent      → single_agent       (clear specialist is already scheduled)
#   ritual     → synthesized_multi  (ceremony requires all voices)
#   liquidity  → random_delegate    (market dynamics need stochastic routing)
_TILE_STRATEGY_MAP: Dict[str, str] = {
    "sigil":       "consensus_pool",
    "agent":       "single_agent",
    "ritual":      "synthesized_multi",
    "liquidity":   "random_delegate",
    "kernel_init": "single_agent",
    "EMPTY":       "single_agent",
}

# ── Sigil tier → additive weight boosts ──────────────────────────────────────
# Applied to BaseAgent.evaluation_weights when a tiered settlement is active.
# Deeper tiers reward more ambitious / novel proposals.
_SIGIL_WEIGHT_BOOSTS: Dict[str, Dict[str, float]] = {
    "base": {},
    "deeper": {
        "goal_alignment":            0.05,
        "swarm_benefit":             0.05,
        "novelty":                   0.05,
    },
    "monolith": {
        "goal_alignment":            0.10,
        "swarm_benefit":             0.10,
        "implementation_feasibility": 0.05,
        "novelty":                   0.10,
    },
}

# Boost TTL in seconds (1 hour)
_BOOST_TTL = 3600


# ── DNA phenotype → meta-rule strings ────────────────────────────────────────
# Tagged with a unique prefix so sync_contract() can replace them cleanly
# on subsequent calls without duplicating stale rules.
_KERNEL_RULE_PREFIXES = (
    "HIGH_METABOLISM:",
    "LOW_METABOLISM:",
    "HIGH_CURVATURE_AFFINITY:",
    "LOW_CURVATURE_AFFINITY:",
    "STRONG_IMMUNITY:",
    "WEAK_IMMUNITY:",
    "HIGH_MUTATION:",
)

def _phenotype_to_meta_rules(phenotype: Dict[str, float]) -> List[str]:
    """Translate kernel DNA phenotype values into contract meta-rule strings."""
    rules: List[str] = []

    mr  = phenotype.get("metabolic_rate", 1.0)
    ca  = phenotype.get("curvature_affinity", 0.5)
    is_ = phenotype.get("immune_strength", 0.5)
    mu  = phenotype.get("mutation_rate", 0.001)

    # Metabolic rate governs response urgency
    if mr > 1.2:
        rules.append(
            "HIGH_METABOLISM: Prefer fast, decisive responses over deliberation. "
            "Reduce consensus rounds."
        )
    elif mr < 0.7:
        rules.append(
            "LOW_METABOLISM: Conserve resources. Defer non-critical proposals to "
            "the next negotiation round."
        )

    # Curvature affinity governs routing complexity
    if ca > 0.7:
        rules.append(
            "HIGH_CURVATURE_AFFINITY: Route complex multi-part requests through "
            "consensus_pool rather than single_agent."
        )
    elif ca < 0.3:
        rules.append(
            "LOW_CURVATURE_AFFINITY: Flatten response paths. single_agent routing "
            "preferred for throughput."
        )

    # Immune strength governs proposal gate strictness
    if is_ > 0.7:
        rules.append(
            "STRONG_IMMUNITY: Reject proposals with implementation_feasibility < 0.4. "
            "High integrity mode active."
        )
    elif is_ < 0.3:
        rules.append(
            "WEAK_IMMUNITY: Accept borderline proposals to maintain throughput. "
            "Relaxed feasibility gating."
        )

    # Mutation rate governs novelty preference
    if mu > 0.005:
        rules.append(
            "HIGH_MUTATION: Organism is in high-mutation phase. "
            "Apply +0.1 bonus to novelty scoring for all proposals."
        )

    return rules


# ── Bridge class ──────────────────────────────────────────────────────────────

class KernelContractBridge:
    """
    Bridges HyperbolicKernel organic state to the NegotiationEngine contract.

    All methods accept an optional ``kernel`` argument; when omitted they
    construct a fresh HyperbolicKernel() snapshot so they are safe to call
    without holding a live kernel reference.
    """

    def __init__(self) -> None:
        self._kernel_available = False
        self._HK = None
        try:
            from hyperbolic_kernel import HyperbolicKernel
            self._HK = HyperbolicKernel
            self._kernel_available = True
        except ImportError:
            pass

    def _get_kernel(self, kernel=None):
        """Return provided kernel or create a fresh snapshot."""
        if kernel is not None:
            return kernel
        if not self._kernel_available:
            return None
        return self._HK()

    # ── 1. Tile topology → response_strategy ──────────────────────────────────

    def derive_response_strategy(self, kernel=None) -> str:
        """
        Count active (non-EMPTY) tile process types on the manifold.
        The most frequent type determines the contract response_strategy.

        Returns
        -------
        str
            One of: "single_agent", "consensus_pool",
                    "synthesized_multi", "random_delegate"
        """
        k = self._get_kernel(kernel)
        if k is None:
            return "single_agent"

        type_counts: Dict[str, int] = {}
        for tile in k.tiles.values():
            ptype = tile.data.get("process", "EMPTY")
            if ptype in ("EMPTY", "kernel_init"):
                continue
            type_counts[ptype] = type_counts.get(ptype, 0) + 1

        if not type_counts:
            return "single_agent"

        dominant = max(type_counts, key=lambda t: type_counts[t])
        return _TILE_STRATEGY_MAP.get(dominant, "single_agent")

    def get_tile_type_distribution(self, kernel=None) -> Dict[str, int]:
        """Return raw tile-type counts for diagnostics / status display."""
        k = self._get_kernel(kernel)
        if k is None:
            return {}
        counts: Dict[str, int] = {}
        for tile in k.tiles.values():
            ptype = tile.data.get("process", "EMPTY")
            counts[ptype] = counts.get(ptype, 0) + 1
        return counts

    # ── 2. Sigil tier → proposal weight boost ─────────────────────────────────

    def get_sigil_weight_boost(self) -> Dict[str, float]:
        """
        Read active_sigil_tier.json from ManifoldMemory.
        Returns additive weight deltas to apply to BaseAgent.evaluation_weights.
        Returns {} (no boost) if no active tier or if the boost has expired.
        """
        try:
            if not _SIGIL_STATE_PATH.exists():
                return {}
            with open(_SIGIL_STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
            tier = state.get("active_tier", "base")
            age  = time.time() - state.get("set_at", 0)
            if age > _BOOST_TTL:
                return {}  # Expired
            return dict(_SIGIL_WEIGHT_BOOSTS.get(tier, {}))
        except Exception:
            return {}

    def set_active_sigil_tier(self, tier: str) -> None:
        """
        Persist the active sigil tier to ManifoldMemory shared state.
        Called by SigilPactAeon immediately after forging a tiered sigil.

        Parameters
        ----------
        tier : str
            One of "base", "deeper", "monolith"
        """
        try:
            _SIGIL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_SIGIL_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "active_tier":        tier,
                        "set_at":             time.time(),
                        "expires_in_seconds": _BOOST_TTL,
                        "boost_deltas":       _SIGIL_WEIGHT_BOOSTS.get(tier, {}),
                    },
                    f,
                    indent=2,
                )
        except Exception:
            pass  # Non-fatal — boost simply won't apply

    def get_active_sigil_tier(self) -> Optional[str]:
        """Return the current active tier string, or None if absent/expired."""
        try:
            if not _SIGIL_STATE_PATH.exists():
                return None
            with open(_SIGIL_STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
            age = time.time() - state.get("set_at", 0)
            if age > _BOOST_TTL:
                return None
            return state.get("active_tier")
        except Exception:
            return None

    # ── 3. Immune response → contract veto ────────────────────────────────────

    def check_immune_veto(self, kernel=None) -> bool:
        """
        Returns True if the immune system should veto incoming proposals.

        Veto triggers when ANY of:
          - >30 % of tiles are in CORRUPT or CRITICAL health state
          - The immune system has ≥1 quarantined tile coordinates

        Returns False if the kernel is unavailable (fail-open for liveness).
        """
        k = self._get_kernel(kernel)
        if k is None:
            return False

        try:
            from hyperbolic_kernel import HealthStatus

            tiles = list(k.tiles.values())
            total = len(tiles)
            if total == 0:
                return False

            critical_count = sum(
                1 for t in tiles
                if t.health in (HealthStatus.CORRUPT, HealthStatus.CRITICAL)
            )
            critical_ratio = critical_count / total

            quarantine_active = len(k.organism.immune.quarantine) > 0

            return critical_ratio > 0.30 or quarantine_active

        except Exception:
            return False  # Fail-open

    def get_immune_veto_reason(self, kernel=None) -> str:
        """Return a human-readable veto reason string for logging."""
        k = self._get_kernel(kernel)
        if k is None:
            return "kernel_unavailable"
        try:
            from hyperbolic_kernel import HealthStatus

            tiles = list(k.tiles.values())
            total = len(tiles)
            critical_count = sum(
                1 for t in tiles
                if t.health in (HealthStatus.CORRUPT, HealthStatus.CRITICAL)
            )
            ratio = critical_count / total if total else 0.0
            q_count = len(k.organism.immune.quarantine)

            return (
                f"immune_veto: {critical_count}/{total} tiles critical "
                f"({ratio:.0%}), {q_count} quarantined"
            )
        except Exception as e:
            return f"immune_veto_check_error: {e}"

    # ── 4. DNA phenotype → contract meta-rules ────────────────────────────────

    def derive_dna_meta_rules(self, kernel=None) -> List[str]:
        """
        Express the current organism DNA phenotype as contract meta-rule strings.
        Returns a list of rule strings to inject into contract['meta_rules'].
        Returns [] if kernel unavailable.
        """
        k = self._get_kernel(kernel)
        if k is None:
            return []
        try:
            phenotype = k.organism.dna.get_phenotype()
            return _phenotype_to_meta_rules(phenotype)
        except Exception:
            return []

    # ── Composite: full contract sync ─────────────────────────────────────────

    def sync_contract(
        self,
        contract: Dict[str, Any],
        kernel=None,
    ) -> Dict[str, Any]:
        """
        Apply all four kernel→contract integrations to a contract dict.

        Changes applied (in-place, returns the modified dict):
          1. contract['response_strategy'] ← tile topology majority vote
          2. contract['meta_rules']        ← DNA phenotype rules injected
             (previous kernel-injected rules are replaced, hand-written
              rules are preserved)
          3. contract['kernel_sync']       ← metadata block for audit trail

        The immune veto and sigil weight boost are NOT applied here —
        they are checked per-proposal in NegotiationEngine.run_negotiation_round().

        Safe to call even if kernel is unavailable; returns contract unchanged.
        """
        k = self._get_kernel(kernel)

        # 1. Response strategy from tile topology
        strategy = self.derive_response_strategy(k)
        contract["response_strategy"] = strategy

        # 2. DNA meta-rules: strip old kernel-injected rules, inject fresh ones
        dna_rules  = self.derive_dna_meta_rules(k)
        kept_rules = [
            r for r in contract.get("meta_rules", [])
            if not any(r.startswith(pfx) for pfx in _KERNEL_RULE_PREFIXES)
        ]
        contract["meta_rules"] = kept_rules + dna_rules

        # 3. Audit metadata
        contract["kernel_sync"] = {
            "synced_at":            time.time(),
            "strategy_source":      "kernel_tile_topology",
            "derived_strategy":     strategy,
            "dna_rules_injected":   len(dna_rules),
            "tile_distribution":    self.get_tile_type_distribution(k),
        }

        return contract

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def status_report(self, kernel=None) -> Dict[str, Any]:
        """
        Return a dict summarising the current bridge state.
        Useful for /organism and /observe pattern command output.
        """
        k = self._get_kernel(kernel)
        return {
            "kernel_available":    self._kernel_available,
            "response_strategy":   self.derive_response_strategy(k),
            "immune_veto_active":  self.check_immune_veto(k),
            "immune_veto_reason":  self.get_immune_veto_reason(k) if self.check_immune_veto(k) else "none",
            "dna_meta_rules":      self.derive_dna_meta_rules(k),
            "active_sigil_tier":   self.get_active_sigil_tier(),
            "sigil_weight_boost":  self.get_sigil_weight_boost(),
            "tile_distribution":   self.get_tile_type_distribution(k),
        }


# ── Module-level singleton ────────────────────────────────────────────────────
bridge = KernelContractBridge()
