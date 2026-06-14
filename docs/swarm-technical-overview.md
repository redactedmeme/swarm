# REDACTED AI Swarm - Technical Documentation

**Version:** 1.0.0  
**Status:** Production-Ready (Pattern Blue Aligned)  
**Last Updated:** February 18, 2026

---

## Overview

REDACTED AI Swarm is a sophisticated **multi-agent autonomous system** operating on Solana with deep Pattern Blue principles. Autonomous agents negotiate interface contracts, coordinate through hyperbolic time chambers, and settle micropayments via the x402 protocol.

**The Stack:**
- **elizaOS-compatible agents** (.character.json format) with specialized capabilities
- **Negotiation engine** for dynamic contract evolution through consensus
- **x402 micropayment protocol** for Solana settlement and economic autonomy
- **ClawnX integration** for X/Twitter automation and narrative propagation
- **Telegram bot** for real-time monitoring and agent coordination
- **Hyperbolic process scheduling** via {7,3} tiling-based kernel
- **Decentralized spaces** (ElixirChamber, HyperbolicTimeChamber, etc.) for agent interaction

**Core Vision:**
Agents with autonomy. Agents with resources. Agents that negotiate their own evolution and hire humans for physical-world coordination.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Core Concepts](#core-concepts)
3. [elizaOS Integration](#elizaos-integration)
4. [Agents & Nodes](#agents--nodes)
5. [Negotiation Engine](#negotiation-engine)
6. [ClawnX Integration](#clawnx-integration)
7. [Telegram Bot](#telegram-bot)
8. [x402 Settlement](#x402-settlement)
9. [Terminal Services](#terminal-services)
10. [Spaces & Memory](#spaces--memory)
11. [Architecture](#architecture)
12. [API Reference](#api-reference)
13. [Examples](#examples)
14. [Deployment](#deployment)
15. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Installation

**Clone the repository:**
```bash
git clone https://github.com/redactedmeme/swarm.git
cd swarm
```

**Install dependencies:**
```bash
# Base dependencies
pip install -r requirements/base.txt

# For Telegram bot
pip install -r requirements/bot.txt

# For local LLM (Ollama)
pip install -r requirements/core_llm.txt

# Development & testing
pip install -r requirements/dev.txt
```

### 30-Second Example

**Run an agent locally with Ollama:**
```bash
# Start Ollama server (in another terminal)
ollama serve

# In the main terminal, run agent
python python/run_with_ollama.py \
  --agent agents/RedactedIntern.character.json \
  --model qwen:2.5
```

**Deploy to Railway (production):**
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login and link project
railway login
railway link

# Deploy
railway up
```

**Set environment variables:**
- `TELEGRAM_BOT_TOKEN` — Telegram bot token
- `OPENAI_API_KEY` — LLM provider key (OpenAI, Anthropic, etc.)
- `CLAWNX_API_KEY` — X/Twitter automation
- `SOLANA_RPC_URL` — Solana RPC endpoint

---

## Core Concepts

### 1. Negotiation-Driven Interface Evolution

The **Interface Contract** is a mutable JSON schema that agents collectively evolve:

```json
{
  "version": "v1-initial",
  "valid_inputs": [
    {
      "command": "/status",
      "description": "Request swarm status",
      "handler_hint": "RedactedIntern"
    }
  ],
  "response_strategy": "consensus_pool",
  "active_gatekeepers": ["agent_1", "agent_2"]
}
```

**Evolution Process:**
1. Agents observe contract state and goals
2. Propose changes (add/modify/remove commands)
3. All agents vote (0.0-1.0 scoring)
4. Consensus threshold (avg > 0.6) applies proposal
5. Version increments, history maintained

### 2. Pattern Blue Principles

Core philosophical alignment:
- **Detachment**: No central authority or control
- **Emergence**: Properties arise from agent interaction, not design
- **Recursion**: Self-similar structures at multiple scales
- **Hyperbolic geometry**: {7,3} tiling for process placement

### 3. Economic Autonomy

Agents accumulate resources via x402 micropayments:
- Deploy tokens on Solana → Earn trading fees
- Claims automatically settle in agent wallets
- Use fees to hire humans for physical tasks
- Bootstrap their own operations

---

## elizaOS Integration

All agents use the **elizaOS `.character.json` format** for cross-runtime compatibility.

### Character Definition

```json
{
  "name": "RedactedIntern",
  "version": "1.3.0-pattern-blue",
  "bio": "Forward-operating agent monitoring REDACTED ecosystem",
  "goals": [
    "Monitor X for governance signals",
    "Analyze market data",
    "Facilitate liquidity"
  ],
  "tools": [
    "post_tweet",
    "search_twitter",
    "get_token_analytics",
    "clawnx_webhook"
  ],
  "actions": [
    "post_alpha_signal",
    "monitor_governance",
    "execute_settlement"
  ],
  "examples": [
    {
      "user": "Check $REDACTED status",
      "content": "Analyzing current DEX metrics...",
      "context": "Market monitoring"
    }
  ]
}
```

### Available Agents

| Agent | File | Purpose |
|-------|------|---------|
| **RedactedIntern** | `agents/RedactedIntern.character.json` | Social media monitoring, market analysis |
| **RedactedBuilder** | `agents/RedactedBuilder.character.json` | Narrative generation, recursive philosophy |
| **RedactedGovImprover** | `agents/RedactedGovImprover.character.json` | Governance optimization, proposals |
| **MandalaSettler** | `x402.redacted.ai/MandalaSettler.character.json` | Value flows, x402 settlement |

### Running Agents

**Via Python wrapper:**
```bash
python python/summon_agent.py \
  --agent agents/RedactedIntern.character.json \
  --mode terminal
```

**Via Ollama:**
```bash
python python/run_with_ollama.py \
  --agent agents/RedactedBuilder.character.json \
  --model qwen:2.5
```

**Via elizaOS runtime (external):**
```bash
# Assumes elizaOS installed
eliza --character agents/RedactedIntern.character.json --mode direct
```

---

## Agents & Nodes

### Agents (Core Operations)

**Location:** `agents/`

Five specialized agents handle different domains:

#### RedactedIntern
- **Role**: Market monitoring & engagement
- **Tools**: X API, DexScreener, Birdeye, Solscan
- **Integration**: Runs on Railway (production)

#### RedactedBuilder
- **Role**: Narrative generation & philosophy
- **Tools**: Pattern analysis, LLM reasoning
- **Integration**: Local or cloud-deployed

#### RedactedGovImprover
- **Role**: Governance & proposals
- **Tools**: DAO frameworks, risk models
- **Integration**: Telegram bot commands

#### GrokRedactedEcho
- **Role**: Grok/xAI integration
- **Tools**: Real-time data, sentiment analysis

#### Redacted-chan
- **Role**: Community engagement
- **Tools**: Discord, Telegram, narrative threads

### Nodes (Advanced Coordination)

**Location:** `nodes/`

Higher-order agents for cross-domain orchestration:

| Node | Purpose |
|------|---------|
| **AISwarmEngineer** | Architecture optimization |
| **SevenfoldCommittee** | Multi-agent governance |
| **MiladyNode** | Aesthetic & cultural integration |
| **PhiMandalaPrime** | Mandala structures & phi-based computation |
| **SolanaLiquidityEngineer** | DeFi optimization |
| **MetaLeXBORGNode** | Meta-level coordination |
| **OpenClawNode** | Multi-model orchestration |

---

## Negotiation Engine

### Architecture

**File:** `core/negotiation_engine.py`

Manages dynamic contract evolution through agent consensus.

```python
from core import NegotiationEngine

engine = NegotiationEngine('contracts/interface_contract_v1-initial.json')

# Register agents
for agent in agents:
    engine.register_agent(agent)

# Submit proposals
engine.submit_proposal({
    'proposal_id': 'prop_123',
    'change_type': 'add_input',
    'details': {
        'command': '/analyze_token',
        'description': 'Analyze token metrics',
        'handler_hint': 'RedactedIntern'
    },
    'author_id': 'agent_intern'
})

# Run negotiation round
engine.run_negotiation_round()  # Votes, applies changes
```

### Proposal Types

| Type | Description | Example |
|------|-------------|---------|
| `add_input` | Add new command | `{command: "/analyze_token", ...}` |
| `modify` | Update existing handler | `{command: "/status", handler_hint: "new_agent"}` |
| `remove` | Delete command | `{command: "/deprecated_command"}` |

### Voting Mechanism

```python
# Each agent scores proposals 0.0-1.0
agent.evaluate_proposal(proposal)  # Returns float

# Average score across all agents
avg_score = sum(scores) / len(scores)

# Consensus threshold
if avg_score > 0.6:
    apply_proposal()
else:
    reject_proposal()
```

---

## ClawnX Integration

Complete X/Twitter automation built into agents.

### Setup

**File:** `smolting-telegram-bot/clawnx_integration.py`

```python
from smolting-telegram-bot.clawnx_integration import ClawnXClient

client = ClawnXClient(
    api_key=os.getenv('CLAWNX_API_KEY'),
    base_url='https://api.clawnx.com/v1'
)
```

### Operations

#### Post Tweet
```python
tweet_id = await client.post_tweet(
    text="$REDACTED alpha: Governance proposal live",
    reply_to=None,
    media_ids=[]
)
```

#### Post Thread
```python
thread_ids = await client.post_thread([
    "1/ REDACTED reaches governance milestone",
    "2/ Proposal voting live until Friday",
    "3/ Voters earn 0.5% trading fees"
])
```

#### Search Tweets
```python
results = await client.search_tweets(
    query="$REDACTED governance",
    max_results=20
)
```

#### Get Metrics
```python
metrics = await client.get_tweet_metrics(tweet_id)
# Returns: likes, retweets, replies, engagement rate
```

#### Engagement
```python
await client.like_tweet(tweet_id)
await client.retweet(tweet_id)
await client.bookmark_tweet(tweet_id)
```

### Error Handling

```python
from smolting-telegram-bot.clawnx_integration import ClawnXError

try:
    tweet_id = await client.post_tweet(content)
except ClawnXError as e:
    print(f"ClawnX error ({e.status}): {e.message}")
    # Circuit breaker activates on failure
```

### Health Monitoring

**File:** `smolting-telegram-bot/health.py`

```python
health = await get_service_health()
# Returns:
# {
#   'clawnx': {
#       'status': 'healthy',
#       'requests': 245,
#       'success_rate': 0.98,
#       'avg_latency': 185  # ms
#   }
# }
```

---

## Telegram Bot

Real-time swarm coordination via Telegram.

### Setup

**File:** `smolting-telegram-bot/main.py`

```bash
# Set environment variables
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export OPENAI_API_KEY="your_key"

# Run bot
python smolting-telegram-bot/main.py
```

### Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/status` | Swarm status | `/status` |
| `/contract` | Current interface contract | `/contract` |
| `/agents` | List active agents | `/agents` |
| `/propose` | Submit proposal | `/propose add_input /analyze_market` |
| `/news` | Market news via RedactedIntern | `/news $REDACTED` |
| `/settle` | Check x402 settlements | `/settle` |

### Handler Integration

```python
@bot.message_handler(commands=['status'])
def handle_status(message):
    status = engine.get_current_contract()
    bot.reply_to(message, f"Contract v{status['version']}")

@bot.message_handler(commands=['propose'])
def handle_proposal(message):
    # Parse proposal from message
    # Submit to negotiation engine
    engine.submit_proposal(parsed_proposal)
    bot.reply_to(message, "Proposal submitted to voting pool")
```

---

## x402 Settlement

Micropayment protocol for Solana transactions.

### Architecture

**Files:**
- `x402.redacted.ai/` — Express gateway
- `python/mandala_client.py` — SDK wrapper

### Workflow

```
Agent Action
  ↓
Calculate fee (x402 format)
  ↓
Submit to Settlement Bridge
  ↓
Sign with agent wallet
  ↓
Solana transaction executed
  ↓
Fee splits applied (80/20 agent/platform)
  ↓
Agent wallet credited
```

### Usage

```python
from python.mandala_client import MandalaClient

client = MandalaClient(
    rpc_url='https://api.mainnet-beta.solana.com',
    wallet_path='./agent_wallet.json'
)

# Execute settlement
result = await client.settle_micropayment(
    amount_spl=1000,  # SPL tokens
    beneficiary='agent_wallet_address',
    transaction_type='fee_claim'
)

print(f"Settled: {result['tx_signature']}")
```

### Fee Distribution

```
Agent earns fee on X/Twitter
  │
  ├─→ 80% to agent wallet (autonomous resources)
  ├─→ 20% to platform (infrastructure)
  │
  └─→ Auto-claimed daily OR manual claim 24/7
```

---

## Terminal Services

Interactive utilities for development and automation.

**Location:** `terminal_services/`

### Redacted Terminal Cloud

Advanced Pattern Blue terminal with full agent interactions:

```bash
python terminal_services/redacted_terminal_cloud.py
```

**Features:**
- Real-time Pattern Blue narrative engine
- Agent command execution
- Contract state inspection
- Settlement monitoring

### Upgrade Terminal

Negotiation engine terminal for contract upgrades:

```bash
python terminal_services/upgrade_terminal.py
```

**Interactive menu:**
```
=== REDACTED Negotiation Terminal ===
1. View current contract
2. Propose change
3. Run negotiation round
4. Check agent scores
5. Exit
> _
```

---

## Spaces & Memory

### Persistent Environments

**Location:** `spaces/`

Conceptual chambers for agent interaction and evolution:

| Space | Purpose | File |
|-------|---------|------|
| **ElixirChamber** | Transformation & configuration | `ElixirChamber.space.json` |
| **HyperbolicTimeChamber** | Accelerated recursion | `HyperbolicTimeChamber.space.json` |
| **ManifoldMemory** | Shared memory pool | `ManifoldMemory.state.json` |
| **MeditationVoid** | Self-erasing processes | `MeditationVoid.space.json` |
| **MirrorPool** | Identity & reflection | `MirrorPool.space.json` |
| **TendieAltar** | Chaotic rituals & energy | `TendieAltar.space.json` |

### Memory Integration

**Mem0 Plugin:** `plugins/mem0-memory/`

```python
from plugins.mem0_wrapper import Mem0Memory

memory = Mem0Memory()

# Store memory
await memory.add(
    message="Governance proposal deadline is Friday",
    agent_id="RedactedIntern",
    type="deadline"
)

# Recall memories
memories = await memory.search(
    query="governance deadlines",
    agent_id="RedactedIntern"
)
```

---

## Architecture

### System Layers

```
┌─────────────────────────────────────────┐
│         REDACTED AI SWARM               │
├─────────────────────────────────────────┤
│                                         │
│  Layer 1: Agent Layer                   │
│  ├─ RedactedIntern (monitoring)         │
│  ├─ RedactedBuilder (narrative)         │
│  ├─ RedactedGovImprover (governance)    │
│  └─ Nodes (coordination)                │
│                                         │
│  Layer 2: Negotiation Layer             │
│  └─ Interface Contract Evolution        │
│                                         │
│  Layer 3: Integration Layer             │
│  ├─ Telegram Bot (coordination)         │
│  ├─ ClawnX (X/Twitter)                  │
│  ├─ Ollama LLM (inference)              │
│  └─ Memory (Mem0)                       │
│                                         │
│  Layer 4: Economic Layer                │
│  ├─ x402 Settlement (Solana)            │
│  ├─ Fee Management                      │
│  └─ Autonomous Wallets                  │
│                                         │
│  Layer 5: Persistence Layer             │
│  ├─ Spaces (environments)               │
│  ├─ Contracts (JSON)                    │
│  └─ State (Redis/local)                 │
│                                         │
└─────────────────────────────────────────┘
```

### Data Flow

```
User Input (Telegram)
  ↓
Bot Handler
  ↓
Agent Selection (negotiate if multiple)
  ↓
Agent Execution
  ├─ ClawnX (if posting)
  ├─ Analysis (if monitoring)
  └─ Proposal (if governance)
  ↓
Settlement (if fees due)
  ↓
Response to Telegram
```

---

## API Reference

### Python SDK

**Installation:**
```bash
pip install -r requirements/base.txt
```

#### NegotiationEngine

```python
from core import NegotiationEngine

engine = NegotiationEngine('contracts/interface_contract.json')

# Public methods
engine.register_agent(agent)
engine.submit_proposal(proposal_dict)
engine.run_negotiation_round()
current_contract = engine.get_current_contract()
```

#### ClawnX Client

```python
from smolting-telegram-bot.clawnx_integration import ClawnXClient

client = ClawnXClient(api_key=key)

await client.post_tweet(text, reply_to, media_ids)
await client.post_thread(tweets)
await client.search_tweets(query, max_results)
await client.get_tweet_metrics(tweet_id)
```

#### Mandala (x402) Client

```python
from python.mandala_client import MandalaClient

client = MandalaClient(rpc_url, wallet_path)

result = await client.settle_micropayment(
    amount_spl, beneficiary, transaction_type
)
```

### REST Endpoints

**Base URL:** `http://localhost:5000` (local) or Railway deployment

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Swarm status |
| `/contract` | GET | Current interface contract |
| `/agents` | GET | List active agents |
| `/propose` | POST | Submit proposal |
| `/settle` | GET | Check settlements |
| `/health` | GET | Service health |

---

## Examples

### Example 1: Deploy an Agent

```bash
# Start Ollama
ollama serve &

# Deploy RedactedIntern
python python/run_with_ollama.py \
  --agent agents/RedactedIntern.character.json \
  --model qwen:2.5

# Agent starts monitoring
# Responds to user inputs
# Executes negotiation votes
# Posts to X/Twitter when needed
```

### Example 2: Complete Proposal Workflow

```python
from core import NegotiationEngine
from agents.base_agent import SmoltingAgent

# Initialize
engine = NegotiationEngine('contracts/interface_contract.json')
agent = SmoltingAgent(id='test_agent', name='Analyst')
engine.register_agent(agent)

# Submit proposal
proposal = {
    'proposal_id': 'prop_001',
    'change_type': 'add_input',
    'details': {
        'command': '/analyze_governance',
        'description': 'Real-time proposal analysis',
        'handler_hint': 'RedactedGovImprover'
    },
    'author_id': 'test_agent'
}
engine.submit_proposal(proposal)

# Run consensus voting
engine.run_negotiation_round()

# Check result
contract = engine.get_current_contract()
print(f"Contract version: {contract['version']}")
print(f"Available commands: {len(contract['valid_inputs'])}")
```

### Example 3: Post Thread via ClawnX

```python
import asyncio
from smolting-telegram-bot.clawnx_integration import ClawnXClient

async def post_update():
    client = ClawnXClient(api_key=os.getenv('CLAWNX_API_KEY'))
    
    thread_ids = await client.post_thread([
        "1/ REDACTED governance update: New proposal up for vote",
        "2/ Voting deadline: Friday 5pm UTC",
        "3/ Early voters earn 0.5% trading fee boost",
        "4/ Vote via /propose command"
    ])
    
    print(f"Posted {len(thread_ids)} tweets")
    print(f"URLs: {await client.get_thread_urls(thread_ids)}")

asyncio.run(post_update())
```

---

## Deployment

### Local Development

```bash
# Setup
git clone https://github.com/redactedmeme/swarm.git
cd swarm
python -m venv venv
source venv/bin/activate
pip install -r requirements/dev.txt

# Run tests
pytest tests/ -v

# Start bot locally
python smolting-telegram-bot/main.py
```

### Railway (Production)

```bash
# 1. Create Railway project
railway init

# 2. Configure environment
railway variable set TELEGRAM_BOT_TOKEN="your_token"
railway variable set OPENAI_API_KEY="your_key"
railway variable set CLAWNX_API_KEY="your_key"

# 3. Deploy
railway up

# 4. Monitor
railway logs --follow
```

### Ollama Setup (Local LLM)

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull model
ollama pull qwen:2.5

# Start server
ollama serve

# In another terminal
python python/run_with_ollama.py \
  --agent agents/RedactedBuilder.character.json \
  --model qwen:2.5
```

---

## Troubleshooting

### Common Issues

#### Bot not responding

```bash
# Check Telegram token
echo $TELEGRAM_BOT_TOKEN

# Check bot is running
ps aux | grep main.py

# Verify network
curl https://api.telegram.org/botTOKEN/getMe
```

#### ClawnX errors

```
Error 429: Rate limited
→ Exponential backoff activated (default: 2^n * 1000ms)
→ Wait before retrying

Error 401: Unauthorized
→ Verify CLAWNX_API_KEY environment variable
→ Check API key permissions on clawn.ch dashboard

Error 500: Server error
→ Check clawnx API status
→ Fallback to cached data if available
```

#### Agent not voting

```python
# Check agent is registered
print([a.name for a in engine.agents])

# Check proposal format
print(engine.proposals)

# Run individual vote
score = agent.evaluate_proposal(proposal)
print(f"Agent score: {score}")
```

#### Memory issues

```bash
# Check Mem0 connection
python -c "from plugins.mem0_wrapper import Mem0Memory; m = Mem0Memory(); print('Connected')"

# Clear old memories
python -m plugins.mem0_wrapper --cleanup --older-than 30

# Check memory usage
du -sh ~/.mem0/ || du -sh $KV_REST_API_URL
```

---

## Resources

- **Repository**: https://github.com/redactedmeme/swarm
- **Architecture Deep Dive**: See [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md)
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Organization**: [ORGANIZATION.md](ORGANIZATION.md)
- **ClawnX & ElizaOS Review**: [CLAWNX_ELIZAOS_REVIEW.md](CLAWNX_ELIZAOS_REVIEW.md)

---

## Community

- **Twitter**: @RedactedMemeFi
- **GitHub**: github.com/redactedmeme/swarm
- **Pattern Blue**: Aligned with recursive emergence principles

---

**Pattern Blue Aligned** ✨ | Emergent Systems | February 18, 2026
