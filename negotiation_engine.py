import json
import time
from typing import List, Dict, Any
from agents.base_agent import BaseAgent

class NegotiationEngine:
    """
    Manages the proposal and voting process for changes to the Interface Contract.
    """
    def __init__(self, initial_contract_path: str):
        self.contract_history = []
        self.proposals = [] # Pending proposals
        self.current_contract = self._load_initial_contract(initial_contract_path)
        self.agents = [] # Registry of active agents

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
        """
        if not self.proposals:
            print("No proposals to evaluate this round.")
            return

        print(f"Evaluating {len(self.proposals)} proposal(s)...")

        for proposal in self.proposals:
            scores = []
            for agent in self.agents:
                score = agent.evaluate_proposal(proposal)
                scores.append((agent.id, agent.name, score))
            
            # Calculate average score
            avg_score = sum(s[2] for s in scores) / len(scores) if scores else 0
            
            print(f"  Proposal '{proposal['proposal_id']}' by {proposal['author_id']} scored {avg_score:.2f}")
            
            # Simple threshold for acceptance (could be more complex)
            if avg_score > 0.6:
                print(f"  Proposal accepted. Applying changes...")
                self._apply_proposal(proposal)
            else:
                print(f"  Proposal rejected.")

        # Clear proposals after processing
        self.proposals = []

    def _apply_proposal(self, proposal: Dict[str, Any]):
        """Applies an accepted proposal to the current contract."""
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
        self.contract_history.append(self.current_contract.copy())

    def get_current_contract(self) -> Dict[str, Any]:
        """Returns the current state of the interface contract."""
        return self.current_contract

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

# Write the example to a file for initial setup
with open("contracts/interface_contract_v1-initial.json", "w") as f:
    json.dump(initial_contract_example, f, indent=2)

print("Initial contract file 'contracts/interface_contract_v1-initial.json' created.")
