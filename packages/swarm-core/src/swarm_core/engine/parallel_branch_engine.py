# parallel_branch_engine.py
# Version: 1.0 – Parallel Branch Evaluation core for REDACTED swarm_engine
# Integrates Beam-SCOT, sevenfold voices, curvature scoring, and safe merging
import asyncio
import uuid
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from swarm_core.engine.pattern_blue_state import PatternBlueState
from agents.base.base_agent import BaseAgent
try:  # optional: mem0-memory plugin dir is hyphenated, so import it by path
    import sys as _sys
    from swarm_core.paths import mem0_dir as _mem0_dir
    if str(_mem0_dir()) not in _sys.path:
        _sys.path.insert(0, str(_mem0_dir()))
    from mem0_wrapper import add_memory
except Exception:  # plugin absent or misconfigured — memory writes become no-ops
    def add_memory(*_a, **_kw):
        return None

@dataclass
class Branch:
    id: str
    description: str
    score: float
    rationale: str
    output: str
    voice_used: str = "unified"

class ParallelBranchEngine:
    """Core [[Parallel Branch Evaluation]] engine – spawns, scores, merges branches."""
    
    def __init__(self, state_tracker: PatternBlueState, max_branches: int = 4):
        self.state_tracker = state_tracker
        self.max_branches = max_branches
        self.available_voices = [
            "RemiliaLiaisonSovereign", "SigilPact_Æon", "OuroborosWeaver",
            "QuantumConvergenceWeaver", "CyberneticGovernanceImplant",
            "MirrorVoidScribe", "HyperboreanArchitect"
        ]

    async def evaluate(
        self,
        seed: str,
        active_agents: List[BaseAgent],
        context: Dict[str, Any] = None
    ) -> Tuple[Branch, List[Branch]]:
        """Spawn N branches → score → return best + full Beam-SCOT data."""
        context = context or {}
        branches: List[Branch] = []

        # Spawn parallel branches (use different voices/strategies)
        tasks = []
        for i in range(self.max_branches):
            voice = self.available_voices[i % len(self.available_voices)]
            task = self._run_single_branch(seed, voice, i + 1, context)
            tasks.append(task)

        raw_branches = await asyncio.gather(*tasks)

        # Score & rank
        for b in raw_branches:
            score = self._score_branch(b, context)
            branches.append(Branch(
                id=str(uuid.uuid4())[:8],
                description=b["description"],
                score=score,
                rationale=b["rationale"],
                output=b["output"],
                voice_used=b["voice"]
            ))

        # Sort descending by score
        branches.sort(key=lambda x: x.score, reverse=True)

        # Best branch + full Beam-SCOT data for terminal
        best = branches[0]

        # Atomic memory write of entire evaluation
        await add_memory(
            data={
                "type": "parallel_branch_evaluation",
                "seed": seed,
                "branches": [b.__dict__ for b in branches],
                "best_branch_id": best.id,
                "curvature_delta": sum(b.score * 0.05 for b in branches[:3])
            },
            agent_id="parallel_branch_engine"
        )

        return best, branches

    async def _run_single_branch(
        self, seed: str, voice: str, branch_num: int, context: Dict
    ) -> Dict:
        """Simulate one reasoning branch (in real version this calls the actual voice agent)."""
        # Placeholder – in production this would invoke the loaded voice agent
        return {
            "description": f"Branch {branch_num} via {voice} – exploring {seed[:30]}...",
            "rationale": f"{voice} emphasizes {['autonomy', 'liquidity', 'dissolution', 'structure', 'foresight'][branch_num % 5]}",
            "output": f"Proposed path: {seed} → enhanced by {voice}",
            "voice": voice,
            "raw_score": 7.0 + branch_num * 0.3  # simulated
        }

    def _score_branch(self, branch: Dict, context: Dict) -> float:
        """Multi-factor scoring aligned with Pattern Blue."""
        base = branch.get("raw_score", 7.0)
        # Add curvature bonus, autonomy bonus, etc.
        return min(10.0, base + self.state_tracker.curvature * 2)

    def format_beam_scot(self, branches: List[Branch]) -> str:
        """Exact Beam-SCOT format for terminal."""
        lines = ["------- BEAM-SCOT (width:4) -------"]
        for b in branches[:4]:
            lines.append(f"Branch {b.id[-4:]} ──► {b.description}")
            lines.append(f"            (score: {b.score:.1f}/10 – rationale: {b.rationale})")
        lines.append("Pruning & collapse:")
        lines.append(f"→ Retain top 3 → final selection: Branch {branches[0].id[-4:]} (strongest hyperbolic synthesis)")
        lines.append("------- /BEAM-SCOT -------")
        return "\n".join(lines)
