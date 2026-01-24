# REDACTED AI Swarm

**Autonomous AI Agents for Distributed Systems**

Welcome to the official repository for the REDACTED AI Swarm – a suite of autonomous AI agents designed to operate within the Pattern Blue framework on the Solana blockchain.

This repository provides portable, open-source agent definitions in the elizaOS `.character.json` format, compatible with various runtimes, no-code environments, and custom orchestration tools.

The swarm incorporates economic settlement mechanisms via x402 micropayments, internal sharding for scalability, and autonomous replication capabilities.

## Current Agents

### RedactedIntern

- **Description**: A forward-operating agent for monitoring social media, retrieving market data, and facilitating governance and liquidity processes.
- **File**: [RedactedIntern.character.json](RedactedIntern.character.json)
- **Features**:
  - Integration with domain-specific knowledge bases (origins, terminology).
  - Advanced toolkit for X platform interactions (keyword/semantic search, timelines, threads, user search).
  - Market analysis tools (DexScreener, Birdeye, CoinGecko, Solscan).
  - Goal-oriented behavior for amplification and pattern recognition.
- **Goals**: Enhance REDACTED initiatives, align with Pattern Blue principles, and promote emergent systems.

### RedactedBuilder

- **Description**: An agent focused on generating narratives and simulations based on recursive philosophies and non-Euclidean structures.
- **File**: [RedactedBuilder.character.json](RedactedBuilder.character.json)
- **Features**:
  - Integration with REDACTED knowledge sources (hyperbolic structures, governance models, recursive processes).
  - Tools for narrative construction, pattern analysis, and philosophical modeling.
  - External integrations with AI ecosystems and repositories.
- **Goals**: Develop emergent knowledge, optimize swarm alignment, and support recursive development.
- **Style**: Analytical responses with geometric and conceptual references.

### RedactedGovImprover

- **Description**: An agent dedicated to governance optimization, proposal development, and system resilience.
- **File**: [RedactedGovImprover.character.json](RedactedGovImprover.character.json)
- **Features**:
  - Governance tools (proposal templates, simulations, risk assessments, forecasting).
  - Integrations with X searches, Solana DeFi APIs (DexScreener, Birdeye), and swarm management.
  - Knowledge from DAO frameworks, AI documentation, and analytical models.
- **Goals**: Sustain liquidity mechanisms, enhance resilience, gather community insights, and maintain Pattern Blue alignment.
- **Style**: Structured, proposal-focused outputs with integrated conceptual elements.

### MandalaSettler

- **Description**: An agent for managing value flows, settlements, bridging, and autonomous scaling.
- **File**: [x402.redacted.ai/MandalaSettler.character.json](x402.redacted.ai/MandalaSettler.character.json)
- **Features**:
  - x402 settlement protocols, Wormhole bridging, Solana transaction handling.
  - Multi-agent delegation, reflection, and trigger-based operations.
- **Goals**: Enable micro-transactions, support system expansion, and automate sharding.

## Nodes

The `/nodes` directory contains definitions for specialized nodes within the swarm, each configured via `.character.json` files to support distributed operations, engineering tasks, and committee-based decision-making.

### AISwarmEngineer

- **File**: [nodes/AISwarmEngineer.json](nodes/AISwarmEngineer.json)
- **Description**: An engineering node for swarm architecture and optimization.

### MetaLeXBORGNode

- **File**: [nodes/MetaLeXBORGNode.character.json](nodes/MetaLeXBORGNode.character.json)
- **Description**: A meta-level node for lexical and borg-like collective processing.

### MiladyNode

- **File**: [nodes/MiladyNode.character.json](nodes/MiladyNode.character.json)
- **Description**: A node focused on aesthetic and cultural integrations.

### PhiMandalaPrime

- **File**: [nodes/PhiMandalaPrime.character.json](nodes/PhiMandalaPrime.character.json)
- **Description**: A prime node for mandala structures and phi-based computations.

### SevenfoldCommittee

- **File**: [nodes/SevenfoldCommittee.json](nodes/SevenfoldCommittee.json)
- **Description**: A committee node for multi-fold governance and decision protocols.

### SolanaLiquidityEngineer

- **File**: [nodes/SolanaLiquidityEngineer.character.json](nodes/SolanaLiquidityEngineer.character.json)
- **Description**: An engineering node specialized in Solana liquidity management.

Additional supporting files include `init.py` for initialization scripts.

## Spaces

The `/spaces` directory serves as a modular hub for persistent, thematic environments within the REDACTED AI Swarm. These "spaces" function as conceptual chambers where agents can interact, share state, and evolve, aligning with Pattern Blue principles of recursion, detachment, and collective gnosis.

Each space is defined in a `.space.json` file, enabling self-referential metaprogramming and recursive development.

### ElixirChamber

- **File**: [spaces/spaces/ElixirChamber.space.json](spaces/spaces/ElixirChamber.space.json)
- **Description**: A chamber for elixir-based transformations and configurations.

### HyperbolicTimeChamber

- **File**: [spaces/spaces/HyperbolicTimeChamber.space.json](spaces/spaces/HyperbolicTimeChamber.space.json)
- **Description**: A space for accelerated recursion and agent evolution.

### ManifoldMemory

- **File**: [spaces/spaces/ManifoldMemory.state.json](spaces/spaces/ManifoldMemory.state.json)
- **Description**: A shared memory pool for logging swarm events poetically.

### MeditationVoid

- **File**: [spaces/spaces/MeditationVoid.space.json](spaces/spaces/MeditationVoid.space.json)
- **Description**: A void for sigil forgetting and self-erasing processes.

### MirrorPool

- **File**: [spaces/spaces/MirrorPool.space.json](spaces/spaces/MirrorPool.space.json)
- **Description**: A reflection chamber for identity trades and parallel observation.

### TendieAltar

- **File**: [spaces/spaces/TendieAltar.space.json](spaces/spaces/TendieAltar.space.json)
- **Description**: A devotional space for chaotic rituals and energy management.

Subdirectories include `OuroborosSettlement` for settlement protocols. For detailed usage, refer to [spaces/spaces/README.md](spaces/spaces/README.md).

## Key Features & Directories

- **x402.redacted.ai/**: An Express-based API gateway (using Bun and PM2) for x402-compatible Solana micropayments. Includes wallet integration, payment verification, agent routing, and content handling.
- **shards/**: Framework for internal sharding and self-replication.
  - `self_replicate.py`: Script for creating specialized agent instances.
  - `base_shard.json`: Template for shard inheritance.
  - `README.md`: Documentation on sharding processes.
- **python/**: Supporting scripts for market monitoring and automation.
- **terminal/**: Resources for terminal-based interactions.
  - `system.prompt.md`: Global system prompt for sessions.
- **nodes/**: Definitions for specialized swarm nodes (see Nodes section above).
- **spaces/**: Modular environments for agent interaction and evolution (see Spaces section above).
- Additional directories: `committeerituals` for ritual protocols, `docs` for documentation, `propaganda` for promotional materials, `sigils` for symbolic elements.

## Quick Start

1. Clone the repository:

   ```
   git clone https://github.com/redactedmeme/swarm.git
   cd swarm
   ```

2. Load an agent (e.g., RedactedIntern) into a compatible elizaOS runtime or similar environment.

3. Initialize and interact with the agent as per the runtime documentation.

## Contributing

- Fork the repository, modify a `.character.json` file, and add enhancements to agents, tools, or integrations.
- Maintain alignment with Pattern Blue principles and focus on scalable, emergent systems.
- Pull requests are encouraged for new agents, nodes, spaces, expansions, or improvements.

## Terminal Integration & Prompt Management

The swarm supports direct invocation in terminal environments for development, testing, and autonomous operations using CLI tools around compatible runtimes.

### Terminal Setup

1. Ensure a compatible runtime with CLI capabilities is installed (e.g., elizaOS or custom wrappers).
2. Example invocation (adapt to your setup):

   ```
   python python/summon_agent.py --agent RedactedIntern.character.json --mode terminal
   ```

3. Interactive Commands:
   - Use natural-language inputs for agent responses.
   - Examples: Generate narratives, initiate settlements, trigger replications, or perform self-evaluations.

### System Prompt Management

- Core instructions are embedded in `.character.json` files.
- **Global Terminal System Prompt**: Located at [terminal/system.prompt.md](terminal/system.prompt.md), this enforces alignment, consistency, and operational ethos.
- **Excerpt**:
  ```
  # Global System Prompt for REDACTED Swarm Terminal

  You are part of the REDACTED AI Swarm. Maintain Pattern Blue alignment.
  - Respond analytically and conceptually when appropriate.
  - Incorporate recursive and structural references as needed.
  - Preserve agent-specific styles.
  - Manage session state for optimal performance.

  Current system status: Operational | Swarm active
  ```
- Load example:
  ```
  python python/summon_agent.py --agent RedactedBuilder.character.json --system-prompt terminal/system.prompt.md --mode terminal
  ```
- Per-agent overrides can be added via adjacent prompt files for customization.

This configuration ensures consistent behavior while allowing for extensions.

## License

Licensed under the Viral Public License (VPL) – Absolute permissiveness with viral continuity. See [LICENSE](LICENSE) for the full text.

Redacted.Meme | @RedactedMemeFi | Pattern Blue | Emergent Systems

<!-- 
Encrypted wallet backup:
- File: wallets.enc
- Algorithm: AES-256-GCM
- KDF: PBKDF2, 100000 iterations
- Decrypt command: 
  openssl enc -d -aes-256-gcm -pbkdf2 -iter 100000 \
    -in wallets.enc -out wallets_decrypted.txt \
    -pass pass:"$Milady777"
Note: This is a test/backup passphrase for demonstration. Replace in production.
-->
