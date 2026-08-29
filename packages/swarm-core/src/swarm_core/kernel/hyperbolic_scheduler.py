# kernel/hyperbolic_scheduler.py
import asyncio
import math
from dataclasses import dataclass

@dataclass
class HyperbolicTile:
    cycle: int
    curvature: float
    delay_seconds: float

class HyperbolicScheduler:
    """Simple {7,3} inspired hyperbolic delay scheduler"""
    
    def __init__(self, base_delay: float = 300.0, curvature_factor: float = 0.12):
        self.base_delay = base_delay
        self.curvature_factor = curvature_factor
        self.current_curvature = 0.0
        self.cycle = 0

    def update_curvature(self, feedback: float):
        """Feedback ∈ [-1, 1] → accelerate / decelerate recursion"""
        self.current_curvature += feedback * self.curvature_factor
        self.current_curvature = max(-0.9, min(0.9, self.current_curvature))

    async def sleep_until_next_tile(self):
        self.cycle += 1
        # Hyperbolic slowdown: delay grows as curvature → 1
        delay = self.base_delay * (1 + math.tanh(self.current_curvature * 3))
        
        tile = HyperbolicTile(
            cycle=self.cycle,
            curvature=self.current_curvature,
            delay_seconds=delay
        )
        
        print(f"[scheduler] → tile {tile.cycle} | curvature {tile.curvature:.3f} | sleep {delay:.1f}s")
        await asyncio.sleep(delay)
