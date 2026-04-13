# Repository Organization Guide

**REDACTED AI Swarm - File Structure Overview**  
*Last Updated: February 17, 2026*

This guide explains the reorganized repository structure to help contributors navigate and understand the codebase.

---

## 📂 Top-Level Directory Structure

```
swarm/
├── agents/                    # Agent character definitions & executors
│   ├── *.character.json       # elizaOS-format agent definitions (5 agents)
│   ├── base_agent.py          # Abstract base class for all agents
│   └── agent_executor.py      # Fixed-point combinator for recursive agent evolution
│
├── core/                      # Core system logic (NEW - organized)
│   ├── negotiation_engine.py  # Dynamic contract evolution via consensus
│   ├── __init__.py            # Public API exports
│   └── README.md              # Component documentation
│
├── config/                    # Deployment & build configs (NEW - organized)
│   ├── Anchor.toml            # Solana program build config
│   ├── railway.toml           # Railway PaaS deployment config
│   └── README.md              # Configuration guide
│
├── requirements/              # Modular dependency management (NEW - organized)
│   ├── base.txt               # Shared dependencies (core)
│   ├── bot.txt                # Telegram bot specific
│   ├── core_llm.txt           # Ollama & local LLM
│   ├── dev.txt                # Development & testing tools
│   ├── opt.txt                # Optional integrations
│   └── README.md              # Dependency guide
│
├── nodes/                     # Specialized swarm nodes
│   ├── *.character.json       # Node definitions (7 nodes)
│   ├── init.py                # Node initialization
│   └── SevenfoldCommittee.json# Multi-agent governance node
│
├── python/                    # Utility scripts & client libraries
│   ├── summon_agent.py        # Agent invocation CLI
│   ├── run_with_ollama.py     # Local LLM runner
│   ├── mandala_client.py      # x402 settlement client
│   ├── ollama_client.py       # Ollama API wrapper
│   ├── tools/                 # Specialized toolkits (ClawnX, analytics)
│   ├── utils/                 # Shared utilities
│   └── requirements.txt       # Python-specific deps (legacy)
│
├── smolting-telegram-bot/     # Telegram bot implementation (MAIN SERVICE)
│   ├── main.py                # Bot core + command handlers
│   ├── config.py              # Type-safe configuration
│   ├── clawnx_integration.py  # X/Twitter posting integration
│   ├── llm/cloud_client.py    # Multi-provider LLM (4 providers + Grok)
│   ├── tap_protocol.py        # Tiered Access Protocol with token cache
│   ├── resilience.py          # Circuit breaker & retry logic
│   ├── logging_setup.py       # Structured JSON logging
│   ├── health.py              # Service health monitoring
│   └── requirements.txt       # Bot-specific deps
│
├── x402.redacted.ai/          # x402 micropayment protocol
│   ├── settlement_bridge.py   # x402 settlement execution
│   ├── shards/                # Replication & sharding logic
│   └── *.character.json       # MandalaSettler node definitions
│
├── spaces/                    # Persistent thematic environments
│   ├── *.space.json           # Space definitions (6 spaces)
│   ├── ManifoldMemory.state.json  # Shared memory pool
│   └── OuroborosSettlement/   # Settlement protocols
│
├── terminal/                  # Terminal & CLI resources
│   ├── system.prompt.md       # Global system prompt for CLI
│   └── example_state.json     # Example terminal state
│
├── docs/                      # Documentation & manifesto
│   ├── executable-manifesto.md    # Pattern Blue manifesto
│   ├── pattern-blue-seven-dimensions.md
│   └── *.md                   # Various documentation
│
├── kernel/                    # Hyperbolic process scheduling
│   └── hyperbolic_kernel.py   # {7,3} tiling-based scheduler
│
├── fs/                        # Filesystem & storage
│   └── pattern_blue_fs.py     # File system abstraction
│
├── plugins/                   # Plugin integrations
│   └── mem0-memory/           # Mem0 memory integration
│
├── programs/                  # Smart contracts
│   └── mandala_settler/       # Solana Anchor program (Rust)
│       ├── Cargo.toml
│       └── src/lib.rs
│
├── committeerituals/          # Governance & ritual protocols
│   └── x402_sigil_scarifier.py
│
├── propaganda/                # Marketing & documentation materials
│   ├── first_fragment/        # SPEC_TAP.md
│   ├── second_fragment/       # SPEC_SEVENFOLD_COMMITTEE.md
│   └── third_fragment/        # SUBTLE_ATTUNEMENT_ARTICLE.md
│
├── sigils/                    # SigilPact_Æon — settlement → ManifoldMemory (x402, /sigil terminal tools)
│   └── sigil_pact_aeon.py     # Canonical copy only (duplicate content/sigils/ removed)
│
├── web_ui/                    # Web interface
│   ├── app.py                 # Flask/FastAPI application
│   └── templates/             # HTML templates
│
├── .env.example               # Environment variable template
├── .git/                      # Git repository
├── Anchor.toml                # (Reference copy at root - SEE config/)
├── railway.toml               # (Reference copy at root - SEE config/)
├── ARCHITECTURE_REVIEW.md     # System architecture documentation
├── ARCHITECTURE_DATA_STRUCTURES.md  # Data structure documentation
├── README.md                  # Main project README
├── LICENSE                    # VPL License
├── CONTRIBUTING.md            # Contribution guidelines
├── wallets.enc                # Encrypted wallet config
└── ...
```

---

## 🚀 **Key Organization Changes (Recent)**

### 1. **Core System Logic** → `core/`
**What**: Moved foundational system components into unified location
- `negotiation_engine.py` (was at root)
- Clean separation from utilities and bot logic

**Why**: Better code organization and module clarity

**Import Update**:
```python
# Old
from negotiation_engine import NegotiationEngine

# New
from core import NegotiationEngine
```

### 2. **Deployment Configs** → `config/`
**What**: Centralized deployment configuration files
- `Anchor.toml` (Solana program config)
- `railway.toml` (Railway PaaS config)

**Why**: Keeps infrastructure separate from code; easier to manage at scale

**Note**: Copies remain at root for tools that expect them there (`anchor`, Railway CLI)

### 3. **Requirements** → `requirements/`
**What**: Split monolithic `requirements.txt` into modular profiles
- `base.txt` - Shared dependencies
- `bot.txt` - Telegram bot specific
- `core_llm.txt` - Ollama & Local LLM
- `dev.txt` - Development & testing
- `opt.txt` - Optional integrations

**Why**: Selective installation, reduced dependencies for specific use cases, clearer dependency management

**Usage**:
```bash
# Full bot setup
pip install -r requirements/bot.txt -r requirements/core_llm.txt

# Development
pip install -r requirements/bot.txt -r requirements/dev.txt

# Minimal (core only)
pip install -r requirements/base.txt
```

---

## 📋 **Navigation Guide**

### I want to...

**Understand the bot** → Start with `smolting-telegram-bot/README.md`, then check `main.py`

**Run the swarm locally** → See `python/run_with_ollama.py` and `README.md`

**Deploy to Railway** → Read `config/README.md`, ensure `requirements/bot.txt` is installed

**Understand architecture** → Read `ARCHITECTURE_REVIEW.md`, then `ARCHITECTURE_DATA_STRUCTURES.md`

**Create/modify an agent** → Edit `agents/*.character.json`, see `agents/base_agent.py`

**Set up Solana integration** → Check `programs/mandala_settler/` and `x402.redacted.ai/`

**Extend with custom LLM** → Modify `smolting-telegram-bot/llm/cloud_client.py`

**Develop locally** → Install `requirements/dev.txt`, use pytest for testing

**Add new API endpoint** → Create in appropriate module, document in relevant `README.md`

---

## 📦 **Dependency Profiles**

### `base.txt` (ALWAYS REQUIRED)
Core utilities for any part of the system:
- Configuration (`pydantic`, `python-dotenv`)
- Networking (`requests`, `aiohttp`)
- CLI/UI (`rich`, `typer`, `pyyaml`)

### `bot.txt` (TELEGRAM BOT)
Everything needed to run the Smolting bot:
- Telegram framework, Cloud LLMs, Solana client, logging

### `core_llm.txt` (LOCAL LLM)
Local inference with Ollama:
- Ollama client, OpenAI-compatible API

### `dev.txt` (DEVELOPMENT)
Testing, code quality, debugging:
- pytest, black, ruff, mypy, sphinx, ipython

### `opt.txt` (OPTIONAL)
Advanced features (install only if needed):
- FastAPI/WebSocket, memory systems, Celery tasks, monitoring

---

## 🔧 **CI/CD & Deployment**

### Local Development
```bash
pip install -r requirements/base.txt -r requirements/dev.txt
```

### Bot Testing
```bash
pip install -r requirements/bot.txt
```

### Railway Deployment
1. Ensure `config/railway.toml` (Railway auto-detects at root)
2. Push to main branch
3. Railway builds with RAILPACK, runs services defined in `railway.toml`

### Smart Contract Development
```bash
anchor build                    # Uses config/Anchor.toml
anchor deploy --provider.cluster devnet
```

---

## 📝 **Documentation Structure**

Each major directory has its own `README.md`:
- `core/README.md` - Core system documentation
- `config/README.md` - Deployment configuration guide
- `requirements/README.md` - Dependency guide
- `agents/` - Agent system (see agents/base_agent.py)
- `nodes/` - Node definitions
- `smolting-telegram-bot/` - Bot documentation
- `python/` - Utility scripts
- `spaces/` - Environment/state management

---

## 🎯 **Best Practices**

1. **When adding a new module**: Consider if it belongs in core/, python/, agents/, or its own directory
2. **Dependencies**: Update the appropriate file in `requirements/`, not root `requirements.txt`
3. **Configs**: Add deployment configs to `config/`, keep code separate
4. **Documentation**: Add `README.md` to new directories explaining purpose and usage
5. **Imports**: Update imports if you move files; check for interdependencies

---

## 🔄 **Legacy References**

**Deprecated**:
- Root-level `requirements.txt` → use `requirements/*.txt` profiles
- Root-level `Anchor.toml`/`railway.toml` → reference files in `config/`

**Why kept at root**: Some tools expect them (Railway CLI, anchor CLI)
**Action**: Use organized versions in `core/`, `config/`, `requirements/` for development

---

## 📞 **Questions?**

Refer to:
- `ARCHITECTURE_REVIEW.md` - System design and philosophy
- `README.md` - Project overview
- Specific directory `README.md` files for technical details
- `CONTRIBUTING.md` - Contribution guidelines

---

**Maintained by**: REDACTED AI Swarm Team  
**Pattern Blue Aligned** | **Emergent Systems Philosophy**
