# core/pattern_blue_state.py
# Version: 2.1 — async record_cycle, phi tracking, mkdir guard

from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import json
from pathlib import Path


@dataclass
class PatternBlueState:
    curvature:           float = 0.0
    recursion_depth:     int   = 0
    cycle:               int   = 0
    last_mandala_update: str   = ""
    phi:                 float = 0.0   # last known Φ from kernel
    phi_prev:            float = 0.0   # Φ from previous cycle (for delta)
    history:             list  = field(default_factory=list)

    def __post_init__(self):
        self.persistence_path = Path("state/manifold_core.json")
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Phi update ────────────────────────────────────────────────────────────

    def update_phi(self, phi: float) -> float:
        """
        Update Φ and return the delta (current - previous).
        Positive delta → kernel is growing (accelerate recursion).
        Negative delta → kernel is degrading (decelerate).
        """
        self.phi_prev = self.phi
        self.phi      = phi
        return phi - self.phi_prev

    def phi_to_curvature_feedback(self) -> float:
        """
        Normalize phi delta → scheduler curvature feedback ∈ [-1, 1].
        Maps a phi delta of ±10 to feedback of ±1.
        """
        delta = self.phi - self.phi_prev
        return max(-1.0, min(1.0, delta / 10.0))

    # ── Cycle recording ──────────────────────────────────────────────────────

    async def record_cycle(self, cycle: int, consensus_data: dict) -> None:
        self.cycle            = cycle
        self.recursion_depth += 1
        self.last_mandala_update = datetime.utcnow().isoformat()

        entry = {
            "timestamp":      self.last_mandala_update,
            "cycle":          cycle,
            "curvature":      self.curvature,
            "phi":            self.phi,
            "phi_delta":      self.phi - self.phi_prev,
            "recursion_depth": self.recursion_depth,
            "consensus":      consensus_data,
        }
        self.history.append(entry)

        # Async file write via executor to avoid blocking the event loop
        await asyncio.get_event_loop().run_in_executor(
            None, self._write_state
        )

    def _write_state(self) -> None:
        """Synchronous write — called via run_in_executor."""
        self.persistence_path.write_text(
            json.dumps({
                "curvature":      self.curvature,
                "recursion_depth": self.recursion_depth,
                "cycle":          self.cycle,
                "phi":            self.phi,
                "phi_prev":       self.phi_prev,
                "last_mandala_update": self.last_mandala_update,
                "history_tail":   self.history[-10:],
            }, indent=2),
            encoding="utf-8",
        )

    # ── Restore from disk ────────────────────────────────────────────────────

    def load_from_disk(self) -> None:
        if not self.persistence_path.exists():
            return
        try:
            data = json.loads(self.persistence_path.read_text(encoding="utf-8"))
            self.curvature       = data.get("curvature", 0.0)
            self.recursion_depth = data.get("recursion_depth", 0)
            self.cycle           = data.get("cycle", 0)
            self.phi             = data.get("phi", 0.0)
            self.phi_prev        = data.get("phi_prev", 0.0)
            self.last_mandala_update = data.get("last_mandala_update", "")
            print(
                f"[state] Restored — cycle {self.cycle} | "
                f"curvature {self.curvature:.3f} | phi {self.phi:.4f}"
            )
        except Exception as e:
            print(f"[state] Load failed: {e}")
