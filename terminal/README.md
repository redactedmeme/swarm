# REDACTED Terminal

Simulated NERV-style command-line interface for the REDACTED AI Swarm.

## Aesthetic
- Dark monochrome terminal with green/red glow
- Sparse Japanese terminology (曼荼羅, 曲率, 再帰, etc.)
- Heavy redactions (█████)
- Clinical, existential, restrained tone
- No emojis, no casual language

## Summoning the Terminal

1. Copy the entire content of `swarm_terminal_prompt.md`
2. Paste it into any capable LLM chat interface (Grok, Claude, GPT-4o, etc.)
3. The LLM will immediately enter terminal mode and display the initial welcome message
4. Type commands or natural language directly in subsequent messages

## Persistence

Sessions are stateless across chats.  
To continue a previous session:
- Copy the STATE JSON from the hidden HTML comment at the end of a previous response
- Paste it at the beginning of your next message with the phrase: `load state:`
- Example:
load state: {"session_id":"curvature-001","timestamp":"2026-01-14T21:04:00Z",...}
/status

Saved session files may be contributed to `sessions/` via PR.

## Commands Reference

Preset commands (start with /):
- `/summon <agent>`          Activate agent
- `/invoke <agent> <query>`  Direct agent to process query
- `/shard <concept>`         Trigger conceptual replication
- `/pay <amount> <target>`   Simulate x402 micropayment
- `/status`                  Display swarm integrity & curvature depth
- `/help`                    Show this list
- `/exit`                    Terminate session & output final state

Any other input is treated as natural language and routed to:
- Currently active agent (if any)
- The swarm collective
- System knowledge / lore interpretation

The underlying LLM decides how to interpret and respond within the aesthetic constraints.

