# HyperbolicScheduler

**File:** `lib/kernel/hyperbolic_scheduler.py`

---

## How It Works

Implements a {7,3}-inspired adaptive delay between swarm cycles. The more the kernel is "growing" (positive Φ delta), the shorter the sleep. Curvature nearing ±0.9 creates dramatic slowdown or speedup.

```
delay = base_delay × (1 + tanh(curvature × 3))
```

At `curvature = 0.0`: `delay = base_delay × 1.0` (neutral)  
At `curvature = 0.9`: `delay = base_delay × 1.997` (nearly 2× slower)  
At `curvature = -0.9`: `delay = base_delay × 0.003` (nearly instant)

---

## API

```python
scheduler = HyperbolicScheduler(base_delay=300.0, curvature_factor=0.12)

scheduler.update_curvature(feedback: float)
# feedback ∈ [-1, 1]  →  curvature += feedback × 0.12
# clamped to [-0.9, 0.9]

await scheduler.sleep_until_next_tile()
# increments cycle, computes delay, sleeps
```

---

## Phi Feedback Wiring

`PatternBlueState.phi_to_curvature_feedback()` maps Φ delta → feedback:

```python
feedback = clamp(delta / 10.0, -1.0, 1.0)
```

A Φ jump of +10 → feedback = +1.0 → curvature += 0.12 → shorter cycles.  
A Φ drop of -10 → feedback = -1.0 → curvature -= 0.12 → longer cycles.

Config: `config/engine.yaml` → `cycles.base_sleep_seconds`
