# Pool Monitor — Raydium / Orca / Meteora

**File:** `redacteddegen-service/pool_monitor.py`

---

## Endpoints

| DEX | Endpoint | Auth | Notes |
|-----|----------|------|-------|
| Raydium AMM | `https://api.raydium.io/v2/main/pairs` | None | Returns all pairs; filter by `liquidity` |
| Orca Whirlpool | `https://api.mainnet.orca.so/v1/whirlpool/list` | None | `body.whirlpools[]` |
| Meteora DLMM | `https://dlmm-api.meteora.ag/pair/all` | None | Filter `hide=true` pairs |

All fetched concurrently via `asyncio.gather`. 30-second in-process cache per source.

---

## PoolData Schema

```python
@dataclass
class PoolData:
    source:        str           # "raydium" | "orca" | "meteora"
    name:          str           # "SOL-USDC"
    address:       str
    liquidity_usd: float
    volume_24h:    float
    fee_apr:       float         # fee-only APR %
    total_apr:     float         # fees + rewards APR %
    token_a:       str
    token_b:       str
    current_price: Optional[float]
    bin_step:      Optional[int]   # Meteora DLMM only
```

---

## IL Calculator

```python
from pool_monitor import compute_il

result = compute_il(entry_price=150.0, current_price=120.0)
# result.il_pct = -3.17%
# result.price_ratio = 0.8
# result.description = "IL -3.17% (price moved 0.800x from entry)"
```

Formula: `IL = 2√k / (1+k) − 1` where `k = current / entry`

---

## Usage

```python
from pool_monitor import get_pool_context, format_pool_context

ctx = await get_pool_context(
    min_liquidity=500_000,   # override global default
    token_filter="SOL",      # only pools containing SOL
)

# ctx["raydium"], ctx["orca"], ctx["meteora"] → list[PoolData]
# ctx["top_by_apr"] → top 5 cross-source by APR

print(format_pool_context(ctx))
```

---

## Env Vars

| Var | Default | Description |
|-----|---------|-------------|
| `POOL_MIN_LIQUIDITY` | `100000` | USD floor for pool inclusion |
| `POOL_MAX_RESULTS` | `10` | Max pools per source |
| `POLL_INTERVAL_SECONDS` | `60` | Main loop poll interval |
| `APR_SPIKE_THRESHOLD` | `50` | % APR to trigger swarm alert |
| `IL_WARN_THRESHOLD` | `-5` | % IL to log warning |
| `IL_EXIT_THRESHOLD` | `-25` | % IL to emit auto-exit signal |
| `SWARM_WEBHOOK_URL` | `` | SwarmInbox endpoint |
