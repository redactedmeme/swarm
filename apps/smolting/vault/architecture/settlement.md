# Settlement & x402

---

## Economic Settlement Flow

Every approved swarm cycle consensus triggers a settlement:

```
consensus approved
  → _settle_economically(consensus)
      → build record {timestamp, cycle, phi, proposal_hash, score, approvals}
      → sha256(record) → tx_sig = "swarm_{hex[:16]}"
      → append to state/settlements.jsonl
      → return tx_sig
  → add_memory("Settled {tx_sig} @ cycle {N}")
```

**Ledger:** `state/settlements.jsonl` — one JSON record per line, append-only.

---

## x402 Payment Gateway

**Service:** `services/x402/` (separate Node.js/Bun service)

Handles pay-per-use API access gated by Solana micropayments. When a payment lands:

1. `SigilBridgeListener.on_settlement(event)` fires
2. Dispatches to `aeon_agent.on_payment_settled(tx_data)` via executor thread
3. Sigil forged in `spaces/OuroborosSettlement/sigil_pact_aeon.py`
4. Chamber logs the settlement event

**`SettlementEvent` fields:** `signature`, `payer`, `amount_lamports`, `endpoint`, `timestamp`

---

## Sigil Bridge

**File:** `services/x402/settlement_bridge.py`

```python
bridge_listener = SigilBridgeListener()
# Activated by payment processor:
await bridge_listener.on_settlement(SettlementEvent(...))
```

Fault-tolerant — if `OuroborosSettlement` chamber not found, runs in observer mode (no sigil, no crash).

---

## Key Files

| File | Purpose |
|------|---------|
| `services/x402/index.js` | Payment gateway entry point |
| `services/x402/agents.js` | Agent routing table |
| `services/x402/settlement_bridge.py` | Solana payment → sigil bridge |
| `services/x402/endpoints/prophecy_ghost.py` | Prophecy endpoint |
| `spaces/OuroborosSettlement/sigil_pact_aeon.py` | Sigil forging |
| `state/settlements.jsonl` | Swarm economic ledger |
