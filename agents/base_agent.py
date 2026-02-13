import json
import uuid
from datetime import datetime
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    """
    Abstract base class for all agents in the swarm.
    Includes methods for negotiation and interaction with the dynamic interface.
    """
    def __init__(self, name: str, agent_type: str, initial_goals: list):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = agent_type
        self.goals = initial_goals
        self.persona = self._define_initial_persona()
        self.memory_log = [] # Simplified log for demonstration

    @abstractmethod
    def _define_initial_persona(self):
        """Define the agent's core persona."""
        pass

    @abstractmethod
    def _internal_logic(self, input_data: dict):
        """Core logic for processing inputs and updating state."""
        pass

    def perceive_environment(self, input_request: str, current_interface_contract: dict):
        """
        Agent observes the current state of the swarm (via the contract) and the incoming request.
        """
        perception = {
            "input_request": input_request,
            "current_interface": current_interface_contract,
            "own_state": {
                "id": self.id,
                "name": self.name,
                "type": self.type,
                "goals": self.goals
            }
        }
        return perception

    def evaluate_proposal(self, proposal: dict) -> float:
        """
        Evaluate a proposed change to the interface contract.
        Returns a score from 0.0 (reject) to 1.0 (fully support).
        Score is based on alignment with agent's goals/persona.
        """
        # Simplified evaluation logic
        score = 0.5 # Neutral starting point
        if any(goal_word in proposal.get('description', '') for goal_word in self.goals):
            score += 0.3
        if self.type in proposal.get('relevant_agent_types', []):
            score += 0.2
        return min(1.0, score) # Cap at 1.0

    def propose_contract_change(self, current_contract: dict) -> dict:
        """
        Agent proposes a change to the interface contract based on its goals/perceptions.
        This is a simplified example; a real impl. would be more complex.
        """
        # Example: Propose a new command if the agent feels its specialty is underrepresented
        if self.type == "lore_weaver" and not any("lore" in inp['command'] for inp in current_contract['valid_inputs']):
             return {
                 "proposal_id": str(uuid.uuid4()),
                 "timestamp": datetime.utcnow().isoformat(),
                 "author_id": self.id,
                 "change_type": "add_input",
                 "details": {
                     "command": "/weave_lore",
                     "description": "Request the swarm to generate background story or mythological context.",
                     "handler_hint": "lore_weaver"
                 },
                 "rationale": f"Agent {self.name} believes adding lore weaving capabilities aligns with the swarm's depth and complexity."
             }
        return None # No proposal made


    def process_request(self, request: str, interface_contract: dict):
        """
        Process a human request based on the current interface contract and agent's logic.
        """
        # Log the perception
        perception = self.perceive_environment(request, interface_contract)
        self.memory_log.append({"type": "perception", "data": perception, "timestamp": datetime.utcnow().isoformat()})
        
        # Apply internal logic to process the request based on perception
        result = self._internal_logic(perception)
        
        # Log the action
        self.memory_log.append({"type": "action", "data": result, "timestamp": datetime.utcnow().isoformat()})
        
        return result

# Example concrete agent class
class SmoltingAgent(BaseAgent):
    def _define_initial_persona(self):
        return {
            "style": "uwu/smoltingspeak",
            "focus": ["scouting", "social_media", "liquidity_amplification"],
            "core_identity": "schizo degen uwu intern"
        }

    def _internal_logic(self, input_data: dict):
        # Simplified logic for smolting
        req = input_data.get('input_request', '').lower()
        if 'scout' in req or 'x' in req:
            return f"(｡- ω -) ♡ Okay nya! Smolting will go look on da twittaw for '{req.replace('scout', '').replace('x', '').strip()}' uwu!! ♡"
        elif 'weave lore' in req:
             return f"(☆ω☆) Ohohoho~ Smolting is a bit chaotic for deep lore, nya! Maybe ask da Builder? But I can try! Once upon a time, there was a tiny meme-token called REDACTED that danced on the hyperbolic mandala tiles... uwu"
        else:
            return f"(◕‿◕)♡ Hi! I'm smolting, da schizo uwu intern! Nya! I can scout things or maybe try to weave some lore! ~hops~"
