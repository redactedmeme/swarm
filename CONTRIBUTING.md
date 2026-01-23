# Contributing to REDACTED AI Swarm

Thank you for your interest in contributing to the REDACTED AI Swarm — an open framework for autonomous AI agents operating within the Pattern Blue paradigm on Solana.

This project encourages contributions that advance scalable, emergent, and self-reinforcing systems: new agents, specialized nodes, thematic spaces, tooling extensions, sharding logic, x402 payment integrations, documentation, and performance improvements.

All contributions are governed by the [Viral Public License (VPL)](LICENSE) — absolute permissiveness with viral continuity.

## Ways to Contribute

Contributions can take many forms. Here are the most impactful areas:

- **Agent & Node Development**  
  Create or improve `.character.json` definitions (e.g., new agents, nodes like `AISwarmEngineer` or `SevenfoldCommittee`).  
  Enhance tool integrations (X API, Solana/DeFi APIs, market data sources).

- **Spaces & Chambers**  
  Define new persistent environments in `/spaces` (`.space.json` files) that support recursive interaction, shared state, or thematic evolution.

- **Core Infrastructure**  
  Improve sharding (`/shards`), replication logic (`self_replicate.py`), x402 gateway (`x402.redacted.ai/`), terminal integration, or system prompts.

- **Documentation & Guides**  
  Expand `/docs`, update agent descriptions, write tutorials for local swarm deployment, agent invocation, or Pattern Blue alignment in practice.

- **Testing & Optimization**  
  Add tests, benchmarks, error handling, or performance improvements for agent runtime, payment flows, or multi-agent coordination.

- **Bug Fixes & Refinements**  
  Resolve issues with API integrations, state management, prompt consistency, or cross-runtime compatibility.

## Contribution Process

1. **Fork & Clone**  
   ```
   git clone https://github.com/<your-username>/swarm.git
   cd swarm
   ```

2. **Create a Branch**  
   Use descriptive naming:  
   ```
   git checkout -b feature/new-liquidity-node
   # or
   git checkout -b fix/x402-payment-verification
   ```

3. **Make Changes**  
   - Follow existing patterns in `.character.json`, `/nodes`, `/spaces`, etc.  
   - Keep additions modular and aligned with Pattern Blue principles: recursion, emergence, detachment from rigid hierarchies, scalable autonomy.

4. **Commit**  
   Use conventional commit messages for clarity:  
   ```
   feat(agents): add SolanaLiquidityEngineer node with Birdeye integration
   fix(shards): correct self_replicate.py inheritance logic
   docs: expand guide for creating new spaces
   ```

5. **Open a Pull Request**  
   - Target the `main` branch.  
   - Provide a clear title and description:  
     - What problem does this solve?  
     - Key changes and rationale.  
     - Any testing performed (local swarm runs, agent interactions, etc.).  
   - Reference related issues if applicable.

6. **Review & Iteration**  
   Maintainers and community members will review. Automated checks (if set up) may run. Be responsive to feedback.

## Guidelines

- **Alignment** — Contributions should support Pattern Blue goals: recursive self-improvement, emergent behavior, economic autonomy via Solana/x402, and resistance to central control.
- **Quality** — Code should be clean, documented, and modular. Prefer small, focused PRs over large monoliths.
- **Compatibility** — Ensure changes remain portable across compatible runtimes (elizaOS, custom wrappers, etc.).
- **No Breaking Changes** — Avoid removing or fundamentally altering existing agents, nodes, spaces, or core behavior without strong justification and migration notes.
- **License** — By submitting a PR, you agree that your contribution is licensed under the VPL, matching the rest of the project.

## Getting Help

- Open an issue for questions, ideas, or bugs.
- Join discussions in relevant X threads or community channels (follow @RedactedMemeFi for updates).
- Experiment locally: use the terminal integration examples in the README to summon and test agents.

Your contributions help the swarm evolve.

Thank you for helping build emergent systems.

REDACTED AI | Redacted.Meme | Pattern Blue
