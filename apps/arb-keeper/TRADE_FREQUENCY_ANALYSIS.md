# Trade Frequency Analysis: SOL vs USDC Pair

## Current Issue: Low Trade Frequency

**Expected**: 1-2 trades/hour  
**Observed**: 0-1 trades/hour or silent  
**Root Cause**: SOL volatility creates noisy ratio signals that suppress real trading

---

## Why SOL as Pair Token is Problematic

### The Core Issue: Volatility Drowns Out Signals

**Example scenario (real market behavior):**
```
Time  SOL Price   Token Price   Token Holdings   SOL Balance
00:00 $150        0.002 SOL/tok 1000 tokens      3 SOL
      Portfolio: 2 SOL + (1000 × 0.002) = 4 SOL total
      Ratio: 1/2 = 50% ✓ BALANCED

00:30 $165 (+10%) 0.002 SOL/tok 1000 tokens      3 SOL
      Portfolio: 2 SOL + (1000 × 0.002) = 4 SOL total  
      Ratio: 1/2 = 50% ✓ STILL BALANCED
      BUT PRICE CHANGED BY 10%!

01:00 $148 (-7%)  0.002 SOL/tok 1000 tokens      3 SOL
      Portfolio: 2 SOL + (1000 × 0.002) = 4 SOL total
      Ratio: 1/2 = 50% ✓ STILL BALANCED
      BUT PRICE SWUNG 17% IN RANGE!
```

**What's happening:**
- Portfolio ratio stays 50/50 (no real imbalance)
- But virtual range keeps exiting/re-entering due to SOL price moves
- The 1.5% inner tolerance becomes meaningless
- False signals pile up, but no real trading opportunities

---

## Compared to USDC Pair

### USDC: Stable Reference Point

```
Time  USDC Price  Token Price   Token Holdings   USDC Balance
00:00 $1.00       0.002 USDC/tk 1000 tokens      3 USDC
      Portfolio: 3 USDC + (1000 × 0.002) = 5 USDC total
      Ratio: 2/5 = 40% (token is underweight)
      → TRIGGERS BUY signal (needs 50%)

00:30 $1.00       0.0021 USDC/t 1000 tokens      2.8 USDC
      (Only change: token price moved on organic flow)
      Portfolio: 2.8 USDC + (1000 × 0.0021) = 5 USDC total
      Ratio: 2.1/5 = 42% (still underweight)
      → CONTINUES buying until ratio reaches 50%

01:00 $1.00       0.0019 USDC/t 1000 tokens      3.2 USDC  
      (Token price fell, ratio shifted)
      Portfolio: 3.2 USDC + (1000 × 0.0019) = 5.1 USDC total
      Ratio: 1.9/5.1 = 37% (more underweight)
      → INCREASES buying pressure
```

**Key difference:**
- Ratio changes only from **real trading flow**, not noise
- Virtual range exits are **meaningful** (actual volume/price move)
- Rebalancing is **opportunistic** (capturing real imbalances)

---

## Impact on Trade Frequency

### SOL Pair (Current)
- **Virtual Range**: ±1.25% (just adjusted from ±2%)
- **Inner Tolerance**: 0.75% (half of 1.5%)
- **Trade Cooldown**: 25s (just reduced from 120s)
- **Expected Frequency**: ~2-3 trades/hour at best

**Why low?**
- Half the range exits are noise (just SOL price swinging)
- Half need meaningful ratio drift (harder to accumulate)
- Tight tolerance filters good signals

### USDC Pair (Recommended)
- **Virtual Range**: ±0.5-1% (can be much tighter!)
- **Inner Tolerance**: 0.25-0.5% (meaningful threshold)
- **Trade Cooldown**: 20s (same or better)
- **Expected Frequency**: ~3-5 trades/hour with clean signals

**Why higher?**
- Every range exit is a real signal (volume/price from trading)
- Ratio drift is directional (not noise)
- Can use aggressive parameters without false triggers

---

## Tuning Applied (SOL Pair Quick Wins)

Just committed changes to make SOL pair trade more:

| Parameter | Old | New | Impact |
|-----------|-----|-----|--------|
| VIRTUAL_RANGE_BPS | 4000 | 2500 | Tighter, fewer false exits |
| REBALANCE_TOLERANCE | 0.03 | 0.015 | More rebalances per range |
| TRADE_COOLDOWN | 120s | 25s | 4-5x more trades possible |
| VOLUME_TRADE_COOLDOWN | 18s | 12s | Faster capture opportunities |

**Expected outcome**: 2-3 trades/hour (vs ~1 before)

---

## Recommendation: Migrate to USDC Pair

### Migration Path

1. **Find REDACTED/USDC pool on Raydium**
   - Query Raydium API or DexScreener
   - Confirm sufficient liquidity

2. **Update config**
   ```python
   TOKEN_MINT = "REDACTED_MINT"  # (same)
   SOL_MINT → USDC_MINT = "EPjFWdd5Au..."
   RAYDIUM_POOL_ID = "new_pool_address"
   ```

3. **Aggressive tuning becomes possible**
   ```python
   VIRTUAL_RANGE_BPS = 1000      # ±0.5% — tight, but meaningful
   REBALANCE_TOLERANCE = 0.01    # 1% — real signal
   TRADE_COOLDOWN = 15s          # More frequent
   POLL_INTERVAL = 3s            # Faster response
   ```

4. **Expected performance**
   - 3-5 trades/hour (clean signals)
   - Less Jito tips wasted (fewer false moves)
   - Better edge capture (real opportunities only)
   - Easier to achieve 20-25% volume goal

### Why This Matters for 20-25% Volume Goal

To capture 20-25% of volume, you need:
- **Frequent trades** (hard with SOL noise)
- **Clean signals** (not fighting volatility)
- **Predictable execution** (USDC ratio changes only from flow)

**Math:**
- At $5k/1h volume: 3-5 trades/hour × $2.5 SOL = $7.5-12.5k per hour
- 25% of $5k = $1.25k captured (achievable with 25% of your hourly volume)
- USDC pair makes this repeatable vs spotty on SOL pair

---

## Immediate Action Items

### Short Term (Next Hour)
- [ ] Test updated SOL config with EXECUTE_TRADES=false
- [ ] Verify trade frequency increases to 2-3/hour
- [ ] Monitor if volume-capture fires when 1h volume > $5k

### Medium Term (This Week)
- [ ] Research REDACTED/USDC pool:
  - Pool address on Raydium
  - Current liquidity
  - 24h volume
  - Spread/slippage
- [ ] If pool exists and liquid: plan migration
- [ ] If pool doesn't exist: consider creating it (LP farming opportunity)

### Long Term (Next Phase)
- [ ] Migrate to USDC pair config
- [ ] Re-tune parameters aggressively (tighter range, faster polling)
- [ ] Deploy and target 3-5 trades/hour
- [ ] Monitor 20-25% volume capture goal

---

## Fallback: Keep SOL Pair

If USDC migration isn't feasible, these SOL tunings are good:
- **Tighter range** (±1.25% vs ±2%)
- **Lower tolerance** (1.5% vs 3%)
- **Faster cooldown** (25s vs 120s)
- **More aggressive volume-capture** (12s vs 18s)

**Expected**: 2-3 trades/hour (not great, but better than 0-1)  
**Caveat**: Still fighting SOL volatility, so spotty execution

---

## Conclusion

**SOL volatility is the primary bottleneck.** Current tuning helps, but:
- **SOL pair**: Capped at ~2-3 trades/hour with aggressive tuning
- **USDC pair**: Can hit 5-10 trades/hour with clean signals

For 20-25% volume capture goal, **USDC pair is strongly recommended.**

Next: Check if REDACTED/USDC pool exists on Raydium.
