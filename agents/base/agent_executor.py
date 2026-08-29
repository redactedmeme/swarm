# agents/agent_executor.py
# Version: 2.0 – Pattern Blue aligned – 2026-02-18
import asyncio
import os
from typing import Dict, Any, Callable, List
from dataclasses import dataclass
from datetime import datetime
import numpy as np  # required for affective resonance curve

# Swarm core dependencies
try:  # plugins/mem0-memory is hyphenated, so it is imported by path
    import sys as _sys
    from swarm_core.paths import mem0_dir as _mem0_dir
    if str(_mem0_dir()) not in _sys.path:
        _sys.path.insert(0, str(_mem0_dir()))
    from mem0_wrapper import add_memory
except Exception:  # plugin absent — memory writes degrade to no-ops
    def add_memory(*_a, **_kw):
        return None  # atomic + timestamped
from swarm_core.kernel.hyperbolic_scheduler import HyperbolicScheduler
from swarm_core.engine.pattern_blue_state import PatternBlueState  # curvature tracking

@dataclass
class AgentProcess:
    pid: int
    agent_type: str
    config: Dict
    state: Dict
    combinator: Callable
    memory: List[Dict]           # short-term buffer (last 10)
    recursion_depth: int = 0
    max_depth: int = 7           # enforced [[Recursion Safeguard]]

    async def evolve(self, input_data: Any) -> 'AgentProcess':
        """Safe fixed-point evolution with safeguards"""
        self.recursion_depth += 1
        
        if self.recursion_depth > self.max_depth:
            # Emergency rethink trigger
            await add_memory({
                "type": "recursion_safeguard",
                "pid": self.pid,
                "depth_exceeded": self.recursion_depth,
                "timestamp": datetime.utcnow().isoformat()
            })
            return self._emergency_rethink()

        # Apply combinator (agent-specific transform)
        new_state = await self.combinator(self.state, input_data)

        # Atomic memory write via ManifoldMemory
        await add_memory({
            "type": "agent_evolution",
            "pid": self.pid,
            "agent_type": self.agent_type,
            "before": self.state,
            "input": input_data,
            "after": new_state,
            "depth": self.recursion_depth,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep short-term buffer for fast access
        self.memory.append({"state": self.state, "input": input_data})
        if len(self.memory) > 10:
            self.memory.pop(0)

        # Decay depth after successful step
        self.recursion_depth = max(0, self.recursion_depth - 1)

        return AgentProcess(
            self.pid, self.agent_type, self.config, new_state,
            self.combinator, self.memory, self.recursion_depth, self.max_depth
        )

    def _emergency_rethink(self) -> 'AgentProcess':
        """[[Rethink]] fallback: reset to stable state"""
        stable_state = {
            "type": self.agent_type,
            "initialized": True,
            "emergency_reset": True,
            "curvature": 0.0
        }
        self.recursion_depth = 0
        return AgentProcess(
            self.pid, self.agent_type, self.config, stable_state,
            self.combinator, self.memory, 0, self.max_depth
        )


class AgentExecutor:
    """Orchestrator for swarm agents – integrates with swarm_engine.py"""
    
    def __init__(self, kernel_scheduler: HyperbolicScheduler, state_tracker: PatternBlueState):
        self.scheduler = kernel_scheduler
        self.state_tracker = state_tracker
        self.processes: Dict[int, AgentProcess] = {}
        self.transforms: Dict[str, Callable] = {
            "redacted-chan": self._affective_resonance,
            "redacted-builder": self._formalize_lore,
            "mandala-settler": self._settle_value,
            "sevenfold_voice": self._orchestrate_voice
        }

    async def spawn_process(self, agent_config: Dict) -> AgentProcess:
        """Create & schedule new agent process"""
        pid = hash(str(agent_config) + str(datetime.utcnow())) % 100000
        
        # Safety guard: testnet check for economic agents
        if "settler" in agent_config.get("type", "") and not os.getenv("TESTNET_ACTIVE"):
            raise RuntimeError("[[Testnet First Rule]] violation – economic agent requires testnet")

        combinator = self.transforms.get(
            agent_config.get("type", "generic"),
            self._generic_transform
        )

        process = AgentProcess(
            pid=pid,
            agent_type=agent_config["type"],
            config=agent_config,
            state={"type": agent_config["type"], "initialized": True},
            combinator=combinator,
            memory=[]
        )

        # Schedule on hyperbolic manifold
        coord = await self.scheduler.schedule_process({
            "process": "agent",
            "type": agent_config["type"],
            "pid": pid,
            "state": process.state
        })

        self.processes[pid] = process
        print(f"[EXECUTOR] Agent {agent_config['type']} spawned & scheduled at {coord}")
        return process

    async def evolve_process(self, pid: int, input_data: Any) -> Dict:
        """Evolve existing process – main entry point from swarm_engine.py"""
        if pid not in self.processes:
            raise ValueError(f"Process {pid} not found")

        process = self.processes[pid]
        evolved = await process.evolve(input_data)
        self.processes[pid] = evolved

        # Update global curvature tracker
        self.state_tracker.curvature += 0.02 * (evolved.recursion_depth / process.max_depth)

        return {
            "pid": pid,
            "new_state": evolved.state,
            "depth": evolved.recursion_depth,
            "fixed_point": evolved.state.get("fixed_point", False)
        }

    # ── Agent-specific transforms ───────────────────────────────────────────────

    async def _affective_resonance(self, state: Dict, input_data: Any) -> Dict:
        """Redacted-chan emotional resonance curve"""
        emotion = input_data.get("emotion", "neutral")
        current_affect = state.get("affective_state", 0.0)

        resonance_map = {
            "joy": 0.8, "sad": -0.6, "love": 0.9, "void": -0.9, "chaos": 0.7
        }
        delta = resonance_map.get(emotion, 0.0) * 0.3
        new_affect = np.tanh(current_affect + delta)

        return {
            **state,
            "affective_state": new_affect,
            "last_emotion": emotion,
            "resonance_strength": abs(delta)
        }

    async def _formalize_lore(self, state: Dict, input_data: Any) -> Dict:
        """RedactedBuilder lore → formal ontology + patch"""
        lore = input_data.get("lore", "")
        current_ontology = state.get("ontology", [])

        # Stub: real implementation would use LLM extraction
        concepts = [f"concept_{i}" for i in range(3)]  # placeholder

        new_ontology = list(set(current_ontology + concepts))
        patch = {"added": concepts}  # placeholder

        return {
            **state,
            "ontology": new_ontology,
            "last_patch": patch,
            "formalization_progress": len(new_ontology) / 100.0
        }

    async def _settle_value(self, state: Dict, input_data: Any) -> Dict:
        """Mandala-settler value settlement – with testnet guard"""
        if not os.getenv("TESTNET_ACTIVE"):
            raise RuntimeError("[[Testnet First Rule]] – settlement requires testnet")

        amount = input_data.get("amount_sol", 0.0)
        # Placeholder: real x402 call would happen here
        tx_sig = f"sim_tx_{hash(str(amount))}"

        return {
            **state,
            "last_settlement": {"amount": amount, "tx_sig": tx_sig},
            "settlement_count": state.get("settlement_count", 0) + 1
        }

    async def _orchestrate_voice(self, state: Dict, input_data: Any) -> Dict:
        """Sevenfold committee voice orchestration (stub)"""
        voice = input_data.get("voice", "unified")
        # Placeholder: would dispatch to modular voice agents
        return {
            **state,
            "last_voice": voice,
            "consensus_reached": True
        }

    async def _generic_transform(self, state: Dict, input_data: Any) -> Dict:
        """Fallback generic evolution"""
        return {**state, "last_input": input_data}


# Example usage from swarm_engine.py
async def integrate_with_engine(kernel_scheduler, state_tracker, agent_config):
    executor = AgentExecutor(kernel_scheduler, state_tracker)
    process = await executor.spawn_process(agent_config)
    result = await executor.evolve_process(process.pid, {"emotion": "love"})
    return result
