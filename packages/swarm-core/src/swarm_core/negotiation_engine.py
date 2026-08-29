import json
import os
import sys
import time
import logging
from typing import List, Dict, Any
from agents.base_agent import BaseAgent

# ── Kernel↔Contract bridge (graceful failure if kernel deps missing) ──────────
try:
    from swarm_core.kernel_contract_bridge import KernelContractBridge as _BridgeClass
    _BRIDGE_AVAILABLE = True
except ImportError:
    _BridgeClass = None
    _BRIDGE_AVAILABLE = False

logger = logging.getLogger(__name__)


class NegotiationEngine:
    """
    Manages the proposal and voting process for changes to the Interface Contract.

    v2.2 additions (Kernel↔Contract bridge):
      - Immune veto gate: proposals blocked when >30% of kernel tiles are
        CORRUPT/CRITICAL or quarantine is active.
      - Sigil tier weight boost: active x402 settlement tier applies additive
        bonuses to agent evaluation weights for the current round.
      - DNA meta-rules sync: kernel phenotype is expressed as contract
        meta-rules after each accepted proposal.
      - Tile topology strategy: response_strategy derived from dominant tile
        process type on the manifold.
    """

    def __init__(self, initial_contract_path: str):
        self.contract_history = []
        self.proposals = []  # Pending proposals
        self.current_contract = self._load_initial_contract(initial_contract_path)
        self.agents = []  # Registry of active agents

        # Kernel bridge (None if kernel deps unavailable)
        self._bridge = _BridgeClass() if _BRIDGE_AVAILABLE else None

        # Sync contract with kernel state on init
        if self._bridge is not None:
            try:
                self._bridge.sync_contract(self.current_contract)
                logger.info("[NegotiationEngine] Kernel↔Contract bridge active.")
            except Exception as _e:
                logger.warning(f"[NegotiationEngine] Bridge sync on init failed: {_e}")

    def _load_initial_contract(self, path: str) -> Dict[str, Any]:
        """Loads the initial contract from a file."""
        with open(path, 'r') as f:
            contract = json.load(f)
        self.contract_history.append(contract.copy())
        return contract

    def register_agent(self, agent: BaseAgent):
        """Registers an agent with the negotiation engine."""
        self.agents.append(agent)

    def submit_proposal(self, proposal: Dict[str, Any]):
        """Adds a proposal to the pending list."""
        self.proposals.append(proposal)

    def run_negotiation_round(self):
        """
        Executes one round of negotiation.
        Agents evaluate proposals and vote.
        The contract is updated based on consensus.

        v2.2: Immune veto gate checked before evaluating any proposals.
              Sigil weight boost applied to agent evaluation weights per round.
        """
        if not self.proposals:
            print("No proposals to evaluate this round.")
            return

        # ── Immune veto gate ──────────────────────────────────────────────────
        if self._bridge is not None:
            try:
                if self._bridge.check_immune_veto():
                    reason = self._bridge.get_immune_veto_reason()
                    print(f"  [IMMUNE VETO] All {len(self.proposals)} proposal(s) blocked. {reason}")
                    logger.warning(f"[NegotiationEngine] Immune veto active: {reason}")
                    self.proposals = []
                    return
            except Exception as _e:
                logger.warning(f"[NegotiationEngine] Immune veto check error: {_e}")

        # ── Sigil weight boost ────────────────────────────────────────────────
        weight_boost: Dict[str, float] = {}
        if self._bridge is not None:
            try:
                weight_boost = self._bridge.get_sigil_weight_boost()
                if weight_boost:
                    tier = self._bridge.get_active_sigil_tier()
                    print(f"  [SIGIL BOOST] Active tier: {tier} — applying weight boost {weight_boost}")
                    logger.info(f"[NegotiationEngine] Sigil weight boost ({tier}): {weight_boost}")
            except Exception as _e:
                logger.warning(f"[NegotiationEngine] Sigil boost retrieval error: {_e}")

        print(f"Evaluating {len(self.proposals)} proposal(s)...")

        for proposal in self.proposals:
            scores = []
            for agent in self.agents:
                # Apply transient sigil boost to agent weights for this round
                original_weights = None
                if weight_boost:
                    original_weights = dict(agent.evaluation_weights)
                    for key, delta in weight_boost.items():
                        if key in agent.evaluation_weights:
                            agent.evaluation_weights[key] = min(
                                1.0,
                                agent.evaluation_weights[key] + delta
                            )

                score = agent.evaluate_proposal(proposal)
                scores.append((agent.id, agent.name, score))

                # Restore original weights after scoring
                if original_weights is not None:
                    agent.evaluation_weights = original_weights

            # Calculate average score
            avg_score = sum(s[2] for s in scores) / len(scores) if scores else 0

            print(f"  Proposal '{proposal['proposal_id']}' by {proposal['author_id']} scored {avg_score:.2f}")

            # Acceptance threshold
            if avg_score > 0.6:
                print(f"  Proposal accepted. Applying changes...")
                self._apply_proposal(proposal)
            else:
                print(f"  Proposal rejected.")

        # Clear proposals after processing
        self.proposals = []

    def _apply_proposal(self, proposal: Dict[str, Any]):
        """
        Applies an accepted proposal to the current contract.

        v2.2: After applying, syncs contract with kernel state (DNA meta-rules
              + tile topology strategy).
        """
        change_type = proposal['change_type']
        details = proposal['details']

        if change_type == "add_input":
            self.current_contract['valid_inputs'].append({
                "command": details['command'],
                "description": details['description'],
                "handler_hint": details.get('handler_hint')
            })
        # Add more change types as needed (modify, remove, etc.)

        # Update metadata
        self.current_contract['version'] = f"v{len(self.contract_history) + 1}"
        self.current_contract['last_updated'] = time.time()

        # ── Kernel sync: inject DNA meta-rules + derived response_strategy ────
        if self._bridge is not None:
            try:
                self._bridge.sync_contract(self.current_contract)
                sync_meta = self.current_contract.get("kernel_sync", {})
                logger.info(
                    f"[NegotiationEngine] Kernel sync post-proposal: "
                    f"strategy={sync_meta.get('derived_strategy')} "
                    f"dna_rules={sync_meta.get('dna_rules_injected', 0)}"
                )
            except Exception as _e:
                logger.warning(f"[NegotiationEngine] Post-proposal kernel sync failed: {_e}")

        self.contract_history.append(self.current_contract.copy())

    def get_current_contract(self) -> Dict[str, Any]:
        """Returns the current state of the interface contract."""
        return self.current_contract

    def sync_with_kernel(self) -> Dict[str, Any]:
        """
        Force a full kernel↔contract sync outside of a proposal round.
        Returns the kernel_sync metadata block for inspection.

        Useful for initializing the contract when the kernel has been
        running for a while and its tile state has diverged.
        """
        if self._bridge is None:
            return {"error": "bridge_unavailable"}
        try:
            self._bridge.sync_contract(self.current_contract)
            return self.current_contract.get("kernel_sync", {})
        except Exception as _e:
            logger.error(f"[NegotiationEngine] Manual kernel sync failed: {_e}")
            return {"error": str(_e)}

    def get_bridge_status(self) -> Dict[str, Any]:
        """
        Return a diagnostic snapshot of the Kernel↔Contract bridge state.
        Includes immune veto status, active sigil tier, DNA meta-rules, and
        derived response_strategy.
        """
        if self._bridge is None:
            return {"bridge_available": False}
        try:
            return self._bridge.status_report()
        except Exception as _e:
            return {"bridge_available": True, "error": str(_e)}

# Example initial contract file content
initial_contract_example = {
  "version": "v1-initial",
  "last_updated": "2026-02-13T00:00:00Z",
  "valid_inputs": [
    {
      "command": "/status",
      "description": "Request the current status or state of the swarm."
    },
    {
      "command": "/request",
      "description": "Make a general request to the swarm."
    }
  ],
  "response_strategy": "single_agent",
  "meta_rules": [
    "Prioritize requests related to Pattern Blue.",
    "Maintain the aesthetic and tone of the swarm."
  ]
}

# Run from repo root to create initial contract: python python/negotiation_engine.py
if __name__ == "__main__":
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _path = os.path.join(_root, "contracts", "interface_contract_v1-initial.json")
    os.makedirs(os.path.dirname(_path), exist_ok=True)
    with open(_path, "w") as f:
        json.dump(initial_contract_example, f, indent=2)
    print(f"Initial contract file created: {_path}")
