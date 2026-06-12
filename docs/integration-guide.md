# Integrate Swarm agents • REDACTED Swarm

> Run privacy-preserving, multi-chain, self-replicating AI agents from the REDACTED Swarm.

![Swarm Banner](https://github.com/redactedmeme/swarm/raw/main/.github/assets/swarm-banner.png)

## Overview

The **REDACTED AI Swarm** is a privacy-first, multi-chain agentic super-organism.  
Agents live as portable `.character.json` files and can be dropped into **any** elizaOS-compatible orchestrator, Ollama, or custom runner.

A Swarm-compatible environment must:

- Discover `.character.json` agents and `.space.json` environments
- Parse metadata (`name`, `bio`, `tools`, `goals`)
- Orchestrate with multi-model LLMs (Claude, Grok, Qwen, Ollama)
- Enable secure on-chain execution via **Phantom MCP**
- Support ZK privacy (Veil), cross-chain bridging (NEAR Intents), and X automation (ClawnX)

---

## Integration Approaches

### 🏠 Local (Ollama) — Privacy-first • Offline-capable
- Full ZK + local LLM
- No API keys needed for core ops
- Perfect for dev & testing

### ☁️ Production (Railway / Docker) — Scalable • Multi-model
- Claude + Grok + Qwen orchestration
- Phantom MCP secure signing
- NEAR Intents 1-click bridging

---

## Quickstart

```bash
# 1. Clone & install
git clone https://github.com/redactedmeme/swarm.git && cd swarm
pip install -r requirements/base.txt -r requirements/core_llm.txt

# 2. Start Ollama
ollama serve & ollama pull qwen2.5

# 3. Run your first agent
python python/run_with_ollama.py \
  --agent agents/RedactedIntern.character.json \
  --model qwen2.5
```

---

## Agent Discovery

Swarm agents live in three folders:

| Folder     | Content                        | Examples                              |
|------------|--------------------------------|---------------------------------------|
| `/agents/` | User agents (`.character.json`)| `RedactedIntern`, `daunted`, `RedactedBuilder` |
| `/nodes/`  | Specialized nodes              | `OpenClawNode`, `SolanaLiquidityEngineer` |
| `/spaces/` | Persistent environments        | `MirrorPool`, `ElixirChamber`         |

---

## Loading Metadata

At startup, only parse the **top-level** fields of each `.character.json`:

```python
import json

def load_swarm_agent(path: str):
    with open(path) as f:
        data = json.load(f)
    
    return {
        "name": data.get("name"),
        "bio": data.get("bio")[:280],           # keep short for context
        "tools": [t["name"] for t in data.get("tools", [])],
        "path": path
    }
```

---

## Injecting into Context

Feed available agents to your LLM in a clean XML-like format:

```xml
<available_swarm_agents>
  <agent>
    <name>RedactedIntern</name>
    <bio>Monitors CT noise and turns it into Pattern Blue liquidity plays...</bio>
    <location>agents/RedactedIntern.character.json</location>
  </agent>
  <agent>
    <name>OpenClawNode</name>
    <bio>Executes secure Phantom MCP signing across Solana + EVM</bio>
    <location>nodes/OpenClawNode.character.json</location>
  </agent>
</available_swarm_agents>
```

---

## Security Considerations

| Feature         | Protection                          |
|-----------------|-------------------------------------|
| **Phantom MCP** | Secure wallet signing — never expose private keys |
| **Veil Cash ZK**| Shielded transactions on Base       |
| **NEAR Intents**| 1-click bridging across 18+ chains  |
| **Ollama local**| Zero data leaves your machine       |

---

## Reference Implementation

The entire [`redactedmeme/swarm`](https://github.com/redactedmeme/swarm) repository **is** the canonical reference.

Includes:
- 20+ pre-built agents
- Railway one-click deploy
- x402 micropayments
- Autonomous replication engine

---

**Ready to replicate?**

[![Fork the Swarm](https://img.shields.io/github/forks/redactedmeme/swarm?style=for-the-badge&logo=github&color=violet)](https://github.com/redactedmeme/swarm/fork)

---

Built with ❤️ for **Pattern Blue** • [Viral Public License (VPL)](https://github.com/redactedmeme/swarm/blob/main/LICENSE)

---

**Questions?** Open an issue or ping `@redactedmeme` on X.
