# Core System Logic

This directory contains the foundational components of the REDACTED AI Swarm.

## Components

### `negotiation_engine.py`
Manages dynamic contract evolution through agent consensus:
- **NegotiationEngine**: Central coordination system
  - Proposal submission and evaluation
  - Consensus-based contract updates
  - History tracking and versioning
  - Threshold-based acceptance (avg score > 0.6)

### Usage

```python
from core import NegotiationEngine
from agents.base_agent import BaseAgent

# Initialize with contract file
engine = NegotiationEngine("contracts/interface_contract_v1-initial.json")

# Register agents
engine.register_agent(agent1)
engine.register_agent(agent2)

# Run negotiation round
engine.run_negotiation_round()

# Get current contract
current = engine.get_current_contract()
```

## Pattern Blue Alignment

These components embody Pattern Blue principles:
- **Detachment**: Agents propose changes without forcing outcomes
- **Emergence**: Contract evolution arises from consensus, not top-down design
- **Recursion**: Contract versions create self-referential history
- **Soft Governance**: No hard-coded rules, only consensus-driven adaptation

---

**Status**: Production | **Version**: 1.0 | **Date**: February 2026
