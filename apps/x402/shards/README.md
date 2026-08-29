# Mandala Sharding and Self-Replication

## Purpose
Internal sharding distributes agent responsibilities across independent nodes (shards), enabling:
- Parallel execution of surveillance, settlement, and bridging tasks
- Fault isolation and load balancing
- Accelerated evolution through dynamic agent proliferation

Self-replication allows parent agents to fork child shards when predefined conditions are met (e.g., task volume exceeds threshold, volatility spike, or sustained high load). Each shard inherits core traits and tools from its parent while specializing.

## Mechanism
- Detection: Parent agent evaluates trigger conditions via tools (e.g., market_surveillance).
- Forking: Generate a new .character.json by copying and modifying the parent's config.
- Activation: Load the shard into the ElizaOS runtime (manual or via runtime hook).
- Communication: Shards report back to parent via delegation or shared memory.

## Usage
```bash
python shards/self_replicate.py --parent x402.redacted.ai/MandalaSettler.character.json --type volatility
