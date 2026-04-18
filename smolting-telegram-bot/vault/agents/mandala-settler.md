# MandalaSettler

**Status:** 📋 Planned — character defined, not yet deployed  
**Character:** `services/x402/MandalaSettler.character.json`

---

## Identity

Settlement executor for x402 micropayments. Manages phi-ratio vaults. Triggers sharding and replication on volatility or load spikes. Uses fixed-point recursion to converge on settlement.

---

## Capabilities

- Execute x402 micropayment settlements
- Shard and replicate on volatility/load
- Fixed-point recursion for settlement convergence
- Sigil payment bridge for intent-triggered micro-flows
- Self-patching node for efficiency optimization

---

## Settlement Flow

1. Payment received at x402 gateway
2. `SigilBridgeListener.on_settlement()` fires
3. MandalaSettler receives settlement event
4. Forges sigil via `aeon_agent.on_payment_settled()`
5. Settlement record written to `state/settlements.jsonl`

---

## Key Files

| File | Purpose |
|------|---------|
| `services/x402/MandalaSettler.character.json` | Character spec (77 lines) |
| `services/x402/settlement_bridge.py` | SigilBridgeListener |
| `spaces/OuroborosSettlement/sigil_pact_aeon.py` | Sigil forging agent |
| `state/settlements.jsonl` | Ledger written by swarm_engine |
