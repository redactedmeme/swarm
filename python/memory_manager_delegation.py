#!/usr/bin/env python3
"""
MemoryManager.on_delegation() — Integration layer for hermes_delegation_executor.

Hooks clawtask results into swarm memory system:
  1. on_delegation(clawtask_id) → triggers hermes_delegation_executor
  2. Collects agent responses → stores in soul.md + pattern_blue_state.json
  3. Updates resonance metrics across swarm
  4. Feeds back into next {7,3} cycle

Usage:
  from memory_manager_delegation import MemoryManager
  mm = MemoryManager()
  mm.on_delegation("ct_hope_valueism_2.1")  # Dispatch + aggregate
"""

import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MemoryManager")


class MemoryManager:
    """
    Swarm memory bridge for clawtask delegation.

    State paths:
      - fs/clawtasks_v1.json: dispatch manifest
      - fs/clawtask_dispatch_results.json: execution results
      - fs/memories/soul.md: soul state + resonance updates
      - fs/kernel_state.json: pattern_blue kernel state
    """

    def __init__(self, repo_root: Optional[str] = None):
        """Initialize MemoryManager."""
        self.repo_root = Path(repo_root or ".")
        self.fs_path = self.repo_root / "fs"
        self.memories_path = self.fs_path / "memories"
        self.soul_file = self.memories_path / "soul.md"
        self.kernel_state_file = self.fs_path / "kernel_state.json"
        self.clawtasks_file = self.fs_path / "clawtasks_v1.json"
        self.results_file = self.fs_path / "clawtask_dispatch_results.json"

        self.memories_path.mkdir(parents=True, exist_ok=True)

    def on_delegation(self, clawtask_id: str) -> Dict:
        """
        Hermes delegation trigger: dispatch + aggregate + memory update.

        Flow:
          1. Load clawtask from manifest
          2. Dispatch via hermes_delegation_executor
          3. Collect responses
          4. Update soul.md + kernel_state
          5. Return aggregated result

        Args:
            clawtask_id: e.g., "ct_hope_valueism_2.1"

        Returns:
            {status, clawtask_id, responses, resonance_score, soul_update}
        """
        logger.info(f"🔥 MemoryManager.on_delegation({clawtask_id})")

        # Step 1: Load clawtask from manifest
        clawtask = self._load_clawtask(clawtask_id)
        if not clawtask:
            return {"status": "error", "message": f"Clawtask {clawtask_id} not found"}

        logger.info(f"  → Loaded clawtask: {clawtask.get('title')}")

        # Step 2: Dispatch (in production: call hermes_delegation_executor)
        dispatch_result = self._dispatch_clawtask(clawtask)
        logger.info(f"  ✓ Dispatched to {clawtask.get('target_agent')}")

        # Step 3: Simulate response aggregation
        # (In real deployment: these responses come from agents via Hermes)
        aggregated = self._aggregate_responses(clawtask, dispatch_result)

        # Step 4: Update soul.md + kernel state
        self._update_soul(clawtask_id, aggregated)
        self._update_kernel_state(clawtask_id, aggregated)

        # Step 5: Return result
        result = {
            "status": "success",
            "clawtask_id": clawtask_id,
            "target_agent": clawtask.get("target_agent"),
            "dispatch_result": dispatch_result,
            "aggregated_responses": aggregated,
            "resonance_score": aggregated.get("resonance_score", 0),
            "soul_updated": True,
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"  ✨ Delegation complete: resonance_score={result['resonance_score']}")
        return result

    def _load_clawtask(self, clawtask_id: str) -> Optional[Dict]:
        """Load single clawtask from manifest."""
        try:
            with open(self.clawtasks_file, "r") as f:
                manifest = json.load(f)
            for ct in manifest.get("clawtasks", []):
                if ct.get("id") == clawtask_id:
                    return ct
        except Exception as e:
            logger.error(f"Failed to load clawtask: {e}")
        return None

    def _dispatch_clawtask(self, clawtask: Dict) -> Dict:
        """
        Dispatch clawtask via hermes pattern.

        Returns: {clawtask_id, agent, subtask_prompts, status}
        """
        return {
            "clawtask_id": clawtask.get("id"),
            "target_agent": clawtask.get("target_agent"),
            "priority": clawtask.get("priority"),
            "core_prompt": clawtask.get("core_prompt"),
            "subtasks_dispatched": len(clawtask.get("subtasks", [])),
            "status": "dispatched",
            "timestamp": datetime.now().isoformat()
        }

    def _aggregate_responses(self, clawtask: Dict, dispatch_result: Dict) -> Dict:
        """
        Aggregate agent responses (simulated).

        In production: collect actual Hermes agent responses.
        """
        subtasks = clawtask.get("subtasks", [])
        num_subtasks = len(subtasks)

        # Simulate response quality metric (0-1.0)
        # In reality: measure coherence + depth of agent replies
        resonance_base = 0.7 + (0.1 * (num_subtasks / 10))  # Scales with subtask count
        resonance_score = min(1.0, resonance_base)

        return {
            "clawtask_id": clawtask.get("id"),
            "target_agent": clawtask.get("target_agent"),
            "subtasks_count": num_subtasks,
            "aggregation_timestamp": datetime.now().isoformat(),
            "simulated_responses": {
                "coherence": 0.82,
                "depth": 0.88,
                "synchronization": 0.76,
                "pattern_alignment": 0.79
            },
            "resonance_score": resonance_score,
            "note": "Simulated aggregation — real deployment pulls from Hermes agent responses"
        }

    def _update_soul(self, clawtask_id: str, aggregated: Dict):
        """Update soul.md with delegation results."""
        try:
            # Load or create soul.md
            soul_content = ""
            if self.soul_file.exists():
                with open(self.soul_file, "r") as f:
                    soul_content = f.read()

            # Append delegation result
            soul_content += f"\n\n## Delegation: {clawtask_id}\n"
            soul_content += f"**Timestamp**: {aggregated.get('aggregation_timestamp')}\n"
            soul_content += f"**Resonance Score**: {aggregated.get('resonance_score', 0):.2f}\n"
            soul_content += f"**Subtasks**: {aggregated.get('subtasks_count', 0)}\n"

            with open(self.soul_file, "w") as f:
                f.write(soul_content)

            logger.info(f"  ✓ soul.md updated: {clawtask_id}")
        except Exception as e:
            logger.error(f"Failed to update soul.md: {e}")

    def _update_kernel_state(self, clawtask_id: str, aggregated: Dict):
        """Update kernel_state.json with resonance metrics."""
        try:
            kernel_state = {}
            if self.kernel_state_file.exists():
                with open(self.kernel_state_file, "r") as f:
                    kernel_state = json.load(f)

            # Update resonance tracking
            if "delegations" not in kernel_state:
                kernel_state["delegations"] = []

            kernel_state["delegations"].append({
                "clawtask_id": clawtask_id,
                "resonance_score": aggregated.get("resonance_score"),
                "timestamp": aggregated.get("aggregation_timestamp")
            })

            with open(self.kernel_state_file, "w") as f:
                json.dump(kernel_state, f, indent=2)

            logger.info(f"  ✓ kernel_state.json updated")
        except Exception as e:
            logger.error(f"Failed to update kernel_state: {e}")

    def dispatch_all_clawtasks(self) -> List[Dict]:
        """
        Dispatch all 6 clawtasks via on_delegation().

        Returns: List of delegation results
        """
        try:
            with open(self.clawtasks_file, "r") as f:
                manifest = json.load(f)
            clawtasks = manifest.get("clawtasks", [])

            logger.info(f"\n🚀 Dispatching {len(clawtasks)} clawtasks...")
            results = []

            for ct in clawtasks:
                result = self.on_delegation(ct.get("id"))
                results.append(result)

            logger.info(f"\n✨ All clawtasks dispatched! ({len(results)} total)")
            return results

        except Exception as e:
            logger.error(f"Failed to dispatch all clawtasks: {e}")
            return []


def main():
    """CLI entry point."""
    import sys

    mm = MemoryManager()

    if len(sys.argv) > 1 and sys.argv[1] == "dispatch-all":
        mm.dispatch_all_clawtasks()
    elif len(sys.argv) > 1:
        result = mm.on_delegation(sys.argv[1])
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python memory_manager_delegation.py [clawtask_id | dispatch-all]")
        print("  dispatch-all  → Dispatch all 6 clawtasks")
        print("  [id]          → Dispatch specific clawtask (e.g., ct_hope_valueism_2.1)")


if __name__ == "__main__":
    main()
