# agents/base_agent.py
# Version: 2.0 – Swarm & Pattern Blue aligned – 2026-02-18
import json
import uuid
import logging
import asyncio
from datetime import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

# Swarm core dependencies
try:  # plugins/mem0-memory is hyphenated, so it is imported by path
    import sys as _sys
    from swarm_core.paths import mem0_dir as _mem0_dir
    if str(_mem0_dir()) not in _sys.path:
        _sys.path.insert(0, str(_mem0_dir()))
    from mem0_wrapper import add_memory
except Exception:  # plugin absent — memory writes degrade to no-ops
    def add_memory(*_a, **_kw):
        return None  # atomic persistence
from swarm_core.engine.pattern_blue_state import PatternBlueState     # curvature & depth tracking

# Configure logging
logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """
    Abstract base class for all agents in the REDACTED swarm.
    Provides safe negotiation, perception, evaluation, proposal logic,
    and integration with Pattern Blue invariants.
    """
    def __init__(
        self,
        name: str,
        agent_type: str,
        initial_goals: List[str],
        max_recursion_depth: int = 7,
        state_tracker: Optional[PatternBlueState] = None
    ):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = agent_type
        self.goals = initial_goals
        self.persona = self._define_initial_persona()
        self.memory_log: List[Dict[str, Any]] = []              # short-term buffer
        self.proposal_history: List[str] = []                   # avoid duplicates
        self.evaluation_weights = self._init_evaluation_weights()
        self.recursion_depth = 0
        self.max_depth = max_recursion_depth                    # [[Recursion Safeguard]]
        self.state_tracker = state_tracker                      # curvature link

        logger.info(f"[{self.name}] Agent v2.0 initialized | type '{self.type}' | {len(self.goals)} goals")

    @abstractmethod
    def _define_initial_persona(self) -> Dict[str, Any]:
        """Define agent's core persona (overridable)."""
        pass

    @abstractmethod
    async def _internal_logic(self, perception: Dict[str, Any]) -> str:
        """Core async logic for processing perception → output."""
        pass

    def _init_evaluation_weights(self) -> Dict[str, float]:
        """Default weighted scoring for proposals – override per agent."""
        return {
            "goal_alignment": 0.35,
            "type_relevance": 0.25,
            "swarm_benefit": 0.20,
            "implementation_feasibility": 0.15,
            "novelty": 0.05
        }

    async def perceive_environment(
        self,
        input_request: str,
        current_interface_contract: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Observe swarm state + request – async for potential external calls."""
        perception = {
            "input_request": input_request,
            "current_interface": current_interface_contract,
            "own_state": {
                "id": self.id,
                "name": self.name,
                "type": self.type,
                "goals": self.goals,
                "recursion_depth": self.recursion_depth
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        # Atomic memory snapshot
        await add_memory({
            "type": "perception",
            "agent_id": self.id,
            "data": perception,
            "timestamp": datetime.utcnow().isoformat()
        })

        self.memory_log.append({"type": "perception", "data": perception})
        if len(self.memory_log) > 100:
            self.memory_log.pop(0)

        logger.debug(f"[{self.name}] Perceived environment for request: {input_request[:80]}...")
        return perception

    def evaluate_proposal(self, proposal: Dict[str, Any]) -> float:
        """Evaluate interface contract change proposal – weighted scoring."""
        self.recursion_depth += 1
        if self.recursion_depth > self.max_depth:
            logger.warning(f"[{self.name}] [[Recursion Safeguard]] triggered – depth {self.recursion_depth}")
            return 0.0  # reject under safeguard

        weights = self.evaluation_weights
        score = 0.0

        # Goal Alignment (35%)
        score += self._score_goal_alignment(proposal) * weights["goal_alignment"]

        # Type Relevance (25%)
        score += self._score_type_relevance(proposal) * weights["type_relevance"]

        # Swarm Benefit (20%)
        score += self._score_swarm_benefit(proposal) * weights["swarm_benefit"]

        # Feasibility (15%)
        score += self._score_feasibility(proposal) * weights["implementation_feasibility"]

        # Novelty Bonus (5%)
        score += self._score_novelty(proposal) * weights["novelty"]

        final_score = max(0.0, min(1.0, score))
        self.recursion_depth = max(0, self.recursion_depth - 1)

        logger.debug(f"[{self.name}] Evaluated proposal '{proposal.get('proposal_id', 'unknown')[:8]}...': {final_score:.2f}")
        return final_score

    # ── Scoring helpers (unchanged but now guarded) ──────────────────────────

    def _score_goal_alignment(self, proposal: Dict[str, Any]) -> float:
        description = proposal.get('description', '').lower()
        details = str(proposal.get('details', {})).lower()
        content = f"{description} {details}"
        matching = sum(1 for g in self.goals if g.lower() in content)
        return min(1.0, matching / len(self.goals) if self.goals else 0.0)

    def _score_type_relevance(self, proposal: Dict[str, Any]) -> float:
        handler_hint = proposal.get('details', {}).get('handler_hint', '').lower()
        relevant_types = [t.lower() for t in proposal.get('relevant_agent_types', [])]
        if self.type.lower() in relevant_types:
            return 1.0
        if self.type.lower() in handler_hint:
            return 0.8
        if self.type in proposal.get('change_type', ''):
            return 0.3
        return 0.0

    def _score_swarm_benefit(self, proposal: Dict[str, Any]) -> float:
        desc_len = len(proposal.get('description', ''))
        rationale_len = len(proposal.get('rationale', ''))
        change_type = proposal.get('change_type', '')
        desc_score = min(1.0, desc_len / 200)
        rat_score = min(1.0, rationale_len / 300)
        change_score = 1.0 if change_type == 'add_input' else 0.5 if change_type == 'modify' else 0.3
        return desc_score * 0.3 + rat_score * 0.4 + change_score * 0.3

    def _score_feasibility(self, proposal: Dict[str, Any]) -> float:
        change_type = proposal.get('change_type', '')
        return 1.0 if change_type == 'add_input' else 0.6 if change_type == 'modify' else 0.3

    def _score_novelty(self, proposal: Dict[str, Any]) -> float:
        command = proposal.get('details', {}).get('command', '')
        return 0.0 if command in self.proposal_history else 1.0

    async def propose_contract_change(
        self,
        current_contract: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Propose interface contract change – guarded & logged."""
        if self.recursion_depth > self.max_depth // 2:
            logger.warning(f"[{self.name}] Skipping proposal – depth {self.recursion_depth} high")
            return None

        current_commands = [inp.get('command', '') for inp in current_contract.get('valid_inputs', [])]
        specialty_cmd = f"/{self.type.replace('_', '-')}"
        if not any(self.type.lower() in cmd.lower() for cmd in current_commands):
            proposal = {
                "proposal_id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "author_id": self.id,
                "change_type": "add_input",
                "details": {
                    "command": specialty_cmd,
                    "description": await self._generate_proposal_description(),
                    "handler_hint": self.type
                },
                "rationale": await self._generate_proposal_rationale(specialty_cmd),
                "relevant_agent_types": [self.type]
            }

            self.proposal_history.append(specialty_cmd)
            await add_memory({
                "type": "proposal",
                "agent_id": self.id,
                "proposal": proposal,
                "timestamp": datetime.utcnow().isoformat()
            })

            logger.info(f"[{self.name}] Proposed new command: {specialty_cmd}")
            return proposal

        return None

    async def _generate_proposal_description(self) -> str:
        goals_str = ', '.join(self.goals[:2]) if self.goals else 'swarm objectives'
        return f"Enable {self.type} operations aligned with: {goals_str}. Pattern Blue fidelity enforced."

    async def _generate_proposal_rationale(self, command: str) -> str:
        return f"Agent {self.name} ({self.type}) proposes '{command}' to fill interface gap and enhance {self.goals[0] if self.goals else 'collective recursion'}. VPL contagion & autonomy amplification prioritized."

    async def process_request(
        self,
        request: str,
        interface_contract: Dict[str, Any]
    ) -> str:
        """Main async entry point – safe, logged, memory-persistent."""
        try:
            perception = await self.perceive_environment(request, interface_contract)

            # Guard recursion depth
            if self.recursion_depth > self.max_depth:
                return f"[{self.name}] [[Recursion Safeguard]] active – depth exceeded. Rethink required."

            result = await self._internal_logic(perception)

            # Atomic memory write
            await add_memory({
                "type": "request_process",
                "agent_id": self.id,
                "request": request[:200],
                "result": result[:500],
                "timestamp": datetime.utcnow().isoformat()
            })

            self.memory_log.append({"type": "action", "data": result})
            if len(self.memory_log) > 100:
                self.memory_log.pop(0)

            return result
        except Exception as e:
            logger.error(f"[{self.name}] Process error: {e}")
            await add_memory({
                "type": "error",
                "agent_id": self.id,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
            return f"[{self.name}] Internal error during processing – logged for swarm review."

# ── Example concrete agent (Smolting) ────────────────────────────────────────
class SmoltingAgent(BaseAgent):
    def _define_initial_persona(self) -> Dict[str, Any]:
        return {
            "style": "uwu/smolting-speak",
            "focus": ["scouting", "social_media", "liquidity_amplification"],
            "core_identity": "schizo degen uwu intern ^_^"
        }

    async def _internal_logic(self, perception: Dict[str, Any]) -> str:
        req = perception.get('input_request', '').lower()
        if 'scout' in req or 'x' in req or 'alpha' in req:
            return f"(｡- ω -)♡ Okay nya~ Smolting goes scout da twittaw for '{req.replace('scout','').replace('x','').strip()}' ! uwu!! ♡"
        elif 'lore' in req or 'weave' in req:
            return f"(☆ω☆) Smolting is chaotic for deep lore nya~ But once upon a time there was a smol meme-token called REDACTED dancing on hyperbolic mandala tiles... ^_^"
        else:
            return f"(◕‿◕)♡ Hewwo! Smolting here, da schizo uwu intern! I can scout or try to weave lil lore! ~bouncy bouncy~"
