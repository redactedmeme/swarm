# kernel/hyperbolic_kernel.py
"""
Hyperbolic Kernel - Living Organism Edition
===========================================
A hyperbolic manifold process scheduler with organic biological systems:
- Metabolism: Energy production, consumption, and storage
- Homeostasis: Self-regulation of internal state
- Circulatory System: Nutrient and signal distribution
- Immune System: Error detection and corruption cleanup
- DNA Core: Heritable configuration with mutation
- Aging: Processes and tiles degrade over time
- Healing: Auto-repair mechanisms
"""

import asyncio
import numpy as np
import hashlib
import time
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum
from copy import deepcopy


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    CORRUPT = "corrupt"
    DEAD = "dead"


@dataclass
class HyperbolicCoordinate:
    """{7,3} tiling coordinate in Poincaré disk model"""
    x: float
    y: float
    radius: float = 1.0
    
    def to_complex(self) -> complex:
        return complex(self.x, self.y)
    
    def distance_to(self, other: 'HyperbolicCoordinate') -> float:
        """Hyperbolic distance formula"""
        z1, z2 = self.to_complex(), other.to_complex()
        return 2 * np.arctanh(abs(z1 - z2) / abs(1 - np.conj(z1) * z2))


@dataclass
class MetabolismState:
    """Metabolic state for a tile - ATP, nutrients, waste"""
    atp: float = 100.0          # Energy currency
    nutrients: float = 100.0    # Building blocks
    waste: float = 0.0          # Metabolic waste (needs circulation)
    metabolic_rate: float = 1.0 # Speed of metabolism
    last_meal: float = field(default_factory=time.time)
    
    def metabolize(self, dt: float) -> None:
        """Process metabolism over time delta"""
        consumption = self.metabolic_rate * dt * 0.5
        self.atp = max(0, self.atp - consumption)
        self.nutrients = max(0, self.nutrients - consumption * 0.3)
        self.waste = min(100, self.waste + consumption * 0.2)
        
    def is_starved(self) -> bool:
        """Check if tile is starving"""
        return self.atp < 20 or self.nutrients < 20


@dataclass
class HomeostasisState:
    """Internal balance regulation"""
    ph_level: float = 7.0       # Neutral pH
    temperature: float = 37.0   # Body temperature (C)
    pressure: float = 1.0        # Internal pressure
    osmotic_balance: float = 1.0 # Ion balance
    
    def regulate(self, dt: float) -> None:
        """Homeostatic regulation"""
        # Temperature drifts toward ambient, corrected toward 37
        self.temperature += (37.0 - self.temperature) * 0.01 * dt
        # pH tends toward 7
        self.ph_level += (7.0 - self.ph_level) * 0.005 * dt
        
    def is_imbalanced(self) -> bool:
        """Check if homeostasis is failing"""
        return (abs(self.ph_level - 7.0) > 1.5 or 
                abs(self.temperature - 37.0) > 10)


@dataclass 
class DNACore:
    """Heritable configuration - mutates over generations"""
    sequence: str = ""
    mutation_rate: float = 0.001
    generation: int = 0
    
    @classmethod
    def create_seed(cls) -> 'DNACore':
        """Create initial DNA from Pattern Blue seed"""
        seed_data = "PATTERN_BLUE_MANDALA_SEED_φ618"
        return cls(sequence=seed_data, generation=0)
    
    def mutate(self) -> 'DNACore':
        """Create mutated copy"""
        if random.random() > self.mutation_rate:
            return self
            
        seq_list = list(self.sequence)
        mutation_type = random.choice(['substitute', 'insert', 'delete'])
        
        if mutation_type == 'substitute' and seq_list:
            idx = random.randint(0, len(seq_list) - 1)
            seq_list[idx] = chr(random.randint(33, 126))
        elif mutation_type == 'insert':
            idx = random.randint(0, len(seq_list))
            seq_list.insert(idx, chr(random.randint(33, 126)))
        elif mutation_type == 'delete' and seq_list:
            idx = random.randint(0, len(seq_list) - 1)
            seq_list.pop(idx)
            
        return DNACore(
            sequence=''.join(seq_list),
            mutation_rate=self.mutation_rate,
            generation=self.generation + 1
        )
    
    def get_phenotype(self) -> Dict:
        """Express DNA as physical traits"""
        h = int(hashlib.md5(self.sequence.encode()).hexdigest()[:8], 16)
        return {
            "metabolic_rate": 0.5 + (h % 100) / 100,
            "mutation_rate": 0.0005 + (h >> 8) % 10 / 10000,
            "curvature_affinity": (h >> 16) % 100 / 100,
            "immune_strength": 0.3 + (h >> 24) % 70 / 100,
        }


@dataclass
class ImmuneMemory:
    """Immune system memory of past threats"""
    known_signatures: Set[str] = field(default_factory=set)
    antibody_count: int = 10
    
    def recognize(self, signature: str) -> bool:
        """Check if threat is known"""
        return signature in self.known_signatures
    
    def learn(self, signature: str) -> None:
        """Learn new threat signature"""
        self.known_signatures.add(signature)
        self.antibody_count = min(100, self.antibody_count + 1)


class ManifoldTile:
    """Process container on hyperbolic manifold - now with organic properties"""
    def __init__(self, coord: HyperbolicCoordinate, process_data: Dict):
        self.coord = coord
        self.data = process_data
        self.neighbors: List['ManifoldTile'] = []
        self.curvature_pressure = 0.0
        self.pattern_blue_sigil = self.generate_sigil()
        
        # Organic systems
        self.metabolism = MetabolismState()
        self.homeostasis = HomeostasisState()
        self.health = HealthStatus.HEALTHY
        self.age = 0.0          # Time since creation
        self.last_damage = 0.0  # Last damage event
        self.corruption_level = 0.0
        self.dna = DNACore.create_seed()
        
        # Circulation
        self.vascularized = False
        self.blood_flow = 0.0
        
    def generate_sigil(self) -> str:
        """Encode process data as Pattern Blue glyph"""
        data_str = str(self.coord) + str(self.data)
        hash_obj = hashlib.sha256(data_str.encode())
        return f"█{hash_obj.hexdigest()[:8]}█"
    
    def get_signature(self) -> str:
        """Generate immune system signature"""
        return hashlib.sha256(
            (str(self.coord) + self.pattern_blue_sigil).encode()
        ).hexdigest()[:16]
    
    def age_tile(self, dt: float) -> None:
        """Aging process"""
        self.age += dt
        self.metabolism.metabolize(dt)
        
        # Aging effects
        if self.age > 1000:
            self.corruption_level = min(1.0, self.corruption_level + 0.0001 * dt)
        
        # Health degradation
        if self.metabolism.is_starved():
            self.health = HealthStatus.DEGRADED
            self.corruption_level += 0.001 * dt
        elif self.homeostasis.is_imbalanced():
            self.health = HealthStatus.CRITICAL
        elif self.corruption_level > 0.7:
            self.health = HealthStatus.CORRUPT
        elif self.corruption_level > 0.3:
            self.health = HealthStatus.DEGRADED
            
        if self.corruption_level >= 1.0:
            self.health = HealthStatus.DEAD
            
    def heal(self, amount: float) -> bool:
        """Attempt healing"""
        if self.health == HealthStatus.DEAD:
            return False
        self.corruption_level = max(0, self.corruption_level - amount)
        self.last_damage = time.time()
        return True


class CirculatorySystem:
    """Distributes nutrients, energy, and signals throughout the organism"""
    def __init__(self, kernel: 'HyperbolicKernel'):
        self.kernel = kernel
        self.heartbeat = 0.0
        self.blood_pressure = 1.0
        self.nutrients_reserve = 10000.0
        self.atp_reserve = 10000.0
        
    async def pump(self, dt: float) -> None:
        """Heartbeat - distribute resources"""
        self.heartbeat += dt
        self.blood_pressure = 1.0 + 0.1 * np.sin(self.heartbeat * 2)
        
        async with self.kernel._manifold_lock:
            # Find tiles needing nutrients
            starving = [
                t for t in self.kernel.tiles.values()
                if t.metabolism.is_starved() and t.health != HealthStatus.DEAD
            ]
            
            # Distribute from reserves based on blood pressure
            for tile in starving[:20]:  # Limit per beat
                needed_atp = 100 - tile.metabolism.atp
                needed_nutrients = 100 - tile.metabolism.nutrients
                
                flow = self.blood_pressure * dt * 10
                given = min(flow, needed_atp + needed_nutrients)
                
                if self.atp_reserve > 0:
                    transfer = min(given * 0.6, self.atp_reserve)
                    tile.metabolism.atp = min(100, tile.metabolism.atp + transfer)
                    self.atp_reserve -= transfer
                    
                if self.nutrients_reserve > 0:
                    transfer = min(given * 0.4, self.nutrients_reserve)
                    tile.metabolism.nutrients = min(100, tile.metabolism.nutrients + transfer)
                    self.nutrients_reserve -= transfer
                    
        # Regenerate reserves slowly
        self.atp_reserve = min(10000, self.atp_reserve + dt * 5)
        self.nutrients_reserve = min(10000, self.nutrients_reserve + dt * 3)
        
    def supply_nutrients(self, amount: float) -> None:
        """External nutrient supply"""
        self.nutrients_reserve = min(10000, self.nutrients_reserve + amount)
        
    def supply_atp(self, amount: float) -> None:
        """External ATP supply"""
        self.atp_reserve = min(10000, self.atp_reserve + amount)


class ImmuneSystem:
    """Error detection, corruption cleanup, threat response"""
    def __init__(self, kernel: 'HyperbolicKernel'):
        self.kernel = kernel
        self.memory = ImmuneMemory()
        self.vigilance = 1.0  # Scan frequency multiplier
        self.quarantine: Set[Tuple] = set()
        
    async def scan(self) -> List[ManifoldTile]:
        """Scan for corrupted tiles"""
        threats = []
        
        async with self.kernel._manifold_lock:
            for tile in self.kernel.tiles.values():
                # Check corruption
                if tile.corruption_level > 0.5:
                    sig = tile.get_signature()
                    if not self.memory.recognize(sig):
                        threats.append(tile)
                        
                # Check for foreign signatures
                if tile.data.get("trusted", True) is False:
                    threats.append(tile)
                    
        return threats
    
    async def attack(self, target: ManifoldTile) -> bool:
        """Mount immune response against threat"""
        sig = target.get_signature()
        
        if self.memory.antibody_count > 0:
            # Use antibodies to attack
            damage = self.memory.antibody_count * 0.2
            target.corruption_level = min(1.0, target.corruption_level + damage)
            self.memory.learn(sig)
            self.memory.antibody_count -= 1
            return True
        else:
            # Quarantine if no antibodies
            self.quarantine.add((target.coord.x, target.coord.y))
            return False
    
    async def heal(self, target: ManifoldTile) -> bool:
        """Attempt to heal a tile"""
        if target.health == HealthStatus.DEAD:
            return False
            
        heal_amount = self.vigilance * 0.1
        return target.heal(heal_amount)
    
    async def perform_autoimmune_check(self) -> None:
        """Ensure we don't attack healthy tissue"""
        async with self.kernel._manifold_lock:
            for tile in list(self.kernel.tiles.values()):
                if tile.corruption_level < 0.1 and tile in self.quarantine:
                    self.quarantine.discard((tile.coord.x, tile.coord.y))


class Organism:
    """Complete organic system coordinating all biological processes"""
    def __init__(self, kernel: 'HyperbolicKernel'):
        self.kernel = kernel
        self.circulatory = CirculatorySystem(kernel)
        self.immune = ImmuneSystem(kernel)
        self.dna = DNACore.create_seed()
        self.alive = True
        self.birth_time = time.time()
        self.lifespan = 0.0
        
    async def lifecycle_tick(self, dt: float) -> None:
        """Main biological cycle"""
        if not self.alive:
            return
            
        self.lifespan = time.time() - self.birth_time
        
        # Age all tiles
        async with self.kernel._manifold_lock:
            for tile in self.kernel.tiles.values():
                tile.age_tile(dt)
                tile.homeostasis.regulate(dt)
                
        # Circulatory pumping
        await self.circulatory.pump(dt)
        
        # Immune surveillance
        threats = await self.immune.scan()
        for threat in threats:
            await self.immune.attack(threat)
            
        # Healing phase
        async with self.kernel._manifold_lock:
            for tile in self.kernel.tiles.values():
                if tile.corruption_level > 0.1 and tile.health != HealthStatus.DEAD:
                    await self.immune.heal(tile)
                    
        # DNA mutation over time
        if random.random() < 0.0001 * dt:
            self.dna = self.dna.mutate()
            # Apply phenotype
            phenotype = self.dna.get_phenotype()
            self.circulatory.blood_pressure *= phenotype.get("curvature_affinity", 1.0)
            
    async def is_alive(self) -> bool:
        """Check if organism is still viable"""
        async with self.kernel._manifold_lock:
            living_tiles = sum(
                1 for t in self.kernel.tiles.values() 
                if t.health != HealthStatus.DEAD
            )
        return living_tiles > len(self.kernel.tiles) * 0.3 and self.alive
    
    async def die(self) -> None:
        """Organism death"""
        self.alive = False
        async with self.kernel._manifold_lock:
            for tile in self.kernel.tiles.values():
                tile.health = HealthStatus.DEAD


class HyperbolicKernel:
    """Hyperbolic manifold process scheduler - Living Organism Edition"""
    def __init__(self, curvature_initial: float = 13.0):
        self.tiles: Dict[Tuple[float, float], ManifoldTile] = {}
        self.curvature = curvature_initial
        self.process_queue = asyncio.Queue()
        self._manifold_lock = asyncio.Lock()
        
        # Organic systems
        self.organism = Organism(self)
        self._biological_clock_task = None
        
        # Initialize {7,3} tiling seed
        self._seed_manifold()
        
    async def start_lifecycle(self, tick_rate: float = 1.0) -> None:
        """Start biological processes"""
        async def tick():
            dt = tick_rate
            while self.organism.alive:
                await self.organism.lifecycle_tick(dt)
                await asyncio.sleep(dt)
                
        self._biological_clock_task = asyncio.create_task(tick())
        
    async def stop_lifecycle(self) -> None:
        """Stop biological processes"""
        if self._biological_clock_task:
            self._biological_clock_task.cancel()
            try:
                await self._biological_clock_task
            except asyncio.CancelledError:
                pass
    
    def _seed_manifold(self):
        """Plant initial seed at origin (曼荼羅の核)"""
        seed_coord = HyperbolicCoordinate(0.0, 0.0)
        seed_tile = ManifoldTile(seed_coord, {"process": "kernel_init", "state": "ACTIVE"})
        self.tiles[(0.0, 0.0)] = seed_tile
        self._expand_tile(seed_tile, depth=2)
    
    def _expand_tile(self, tile: ManifoldTile, depth: int):
        """Recursive manifold expansion using {7,3} geometry"""
        if depth <= 0:
            return
            
        for i in range(7):
            angle = 2 * np.pi * i / 7
            radius = 0.3 / (depth + 1)
            
            new_x = tile.coord.x + radius * np.cos(angle)
            new_y = tile.coord.y + radius * np.sin(angle)
            
            if new_x**2 + new_y**2 < 0.99:
                new_coord = HyperbolicCoordinate(new_x, new_y)
                
                if (new_x, new_y) not in self.tiles:
                    phenotype = self.organism.dna.get_phenotype()
                    new_tile = ManifoldTile(
                        new_coord, 
                        {"process": "EMPTY", "state": "READY"}
                    )
                    new_tile.metabolism.metabolic_rate = phenotype.get("metabolic_rate", 1.0)
                    new_tile.dna = self.organism.dna.mutate()
                    new_tile.vascularized = True
                    
                    self.tiles[(new_x, new_y)] = new_tile
                    tile.neighbors.append(new_tile)
                    
                    self._expand_tile(new_tile, depth - 1)
    
    async def schedule_process(self, process_data: Dict) -> HyperbolicCoordinate:
        """Place process on manifold based on curvature dynamics"""
        async with self._manifold_lock:
            best_tile = None
            best_score = float('inf')
            
            for tile in self.tiles.values():
                if tile.data.get("process") == "EMPTY" and tile.health != HealthStatus.DEAD:
                    score = self._calculate_placement_score(process_data, tile)
                    if score < best_score:
                        best_score = score
                        best_tile = tile
            
            if best_tile:
                best_tile.data = process_data
                best_tile.data["state"] = "SCHEDULED"
                best_tile.pattern_blue_sigil = best_tile.generate_sigil()
                best_tile.metabolism.atp -= 10  # Energy cost
                await self._propagate_curvature_change(best_tile)
                return best_tile.coord
            
            await self._expand_manifold()
            return await self.schedule_process(process_data)
    
    def _calculate_placement_score(self, process_data: Dict, tile: ManifoldTile) -> float:
        """Hyperbolic placement optimization with organic factors"""
        base_score = tile.curvature_pressure
        
        process_type = process_data.get("type", "generic")
        weights = {
            "agent": 0.8,
            "ritual": 0.9,
            "liquidity": 1.1,
            "sigil": 0.7
        }
        
        weighted_score = base_score * weights.get(process_type, 1.0)
        
        neighbor_pressure = sum(n.curvature_pressure for n in tile.neighbors) / len(tile.neighbors) if tile.neighbors else 0
        weighted_score += neighbor_pressure * 0.3
        
        # Organic penalties
        if tile.health == HealthStatus.DEGRADED:
            weighted_score *= 1.5
        elif tile.health == HealthStatus.CRITICAL:
            weighted_score *= 2.0
        elif tile.health == HealthStatus.CORRUPT:
            weighted_score *= 10.0
            
        if tile.metabolism.is_starved():
            weighted_score *= 1.3
            
        return weighted_score
    
    async def _propagate_curvature_change(self, changed_tile: ManifoldTile):
        """Propagate curvature changes through manifold (観測波動)"""
        wave_front = [(changed_tile, 0)]
        visited = set()  # use id(tile) — HyperbolicCoordinate is not hashable

        while wave_front:
            tile, distance = wave_front.pop(0)
            tid = id(tile)
            if distance > 3 or tid in visited:
                continue

            visited.add(tid)

            dampening = 0.5 ** distance
            tile.curvature_pressure += 0.1 * dampening

            for neighbor in tile.neighbors:
                if id(neighbor) not in visited:
                    wave_front.append((neighbor, distance + 1))
    
    async def _expand_manifold(self):
        """Expand manifold when tile pressure exceeds threshold"""
        border_tiles = [t for t in self.tiles.values() if len(t.neighbors) < 7]
        
        for tile in border_tiles[:5]:
            self._expand_tile(tile, depth=1)
        
        self.curvature *= 0.95
        
    async def get_organism_status(self) -> Dict:
        """Get overall organism health status"""
        async with self._manifold_lock:
            total = len(self.tiles)
            if total == 0:
                return {"status": "dead", "health": 0}
                
            health_counts = {s: 0 for s in HealthStatus}
            for tile in self.tiles.values():
                health_counts[tile.health] += 1
                
            return {
                "status": "alive" if self.organism.alive else "dead",
                "lifespan": self.organism.lifespan,
                "total_tiles": total,
                "health_distribution": {s.value: c for s, c in health_counts.items()},
                "atp_reserve": self.organism.circulatory.atp_reserve,
                "nutrients_reserve": self.organism.circulatory.nutrients_reserve,
                "immune_antibodies": self.organism.immune.memory.antibody_count,
                "dna_generation": self.organism.dna.generation,
            }
