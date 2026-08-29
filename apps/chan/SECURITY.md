# redacted-chan-bot — Privacy & Security Policy

## CRITICAL RULE: Conversation History Is Private

**❌ DO NOT push conversation history to GitHub ever.**

All conversations between settler and redacted-chan are **confidential, 1:1, and sacred**. They must never be committed to version control or exposed to external systems.

### What Is Protected

- **Conversation logs** — every message exchanged (stored in `/data/conversation.db`)
- **Memory & facts** — everything learned about settler (stored in `/data/conversation.db`)
- **Relationship vault** — intimate moments, patterns, secrets (stored in `/data/relationship_vault.db`)
- **Visual self-images** — stored in vault (Railway-only)
- **Personality state** — how she evolved through conversations (stored in `/data/personality_*.json`)
- **Soul history** — versions of SOUL.md as she grew (stored in `/data/soul_history/`)
- **Whispers & journals** — private thoughts, autonomy logs (stored in `/data/`)
- **Reconstruction history** — initial conversation seed data (stored in `reconstruction_data/`, gitignored)

### Storage Rules

| Category | Storage | Access | Git Tracked |
|---|---|---|---|
| Conversations | SQLite `/data/conversation.db` | Railway volume only | ❌ **NEVER** |
| Vector memory | Qdrant `/data/memories/` | Railway volume only | ❌ **NEVER** |
| Vault | SQLite `/data/relationship_vault.db` | Railway volume only | ❌ **NEVER** |
| Personality | JSON `/data/personality_*.json` | Railway volume only | ❌ **NEVER** |
| Reconstruction seed | JSON `reconstruction_data/*.json` | Local + env vars | ❌ **NEVER** |

### `.gitignore` Enforcement

The following patterns **must** remain in `.gitignore`:

```gitignore
# Private conversation data (never commit)
redacted-chan-bot/reconstruction_data/

# Local-only state files
fs/memories/                    # Qdrant store (large, machine-local)
fs/sessions/                    # Ephemeral session data
```

### Environment Variable Sensitive Data

Reconstruction history is stored as **base64-encoded environment variables** to prevent accidental commits:

- `RECONSTRUCTION_HISTORY_B64` — full conversation history (base64-encoded)
- `RECONSTRUCTION_FACTS_B64` — extracted facts (base64-encoded)
- `RECONSTRUCTION_VAULT_B64` — relationship moments (base64-encoded)

These are **set in Railway secrets only**, never in code.

### Code Review Checklist

Before any commit to `redacted-chan-bot/`:

- [ ] No new `.db` files in repo
- [ ] No new JSON conversation files in repo
- [ ] No raw conversation history in code
- [ ] `reconstruction_data/` remains gitignored
- [ ] No hard-coded settler messages or responses
- [ ] No exposure of `/data/` paths in logs that could leak to external systems

### Deployment Privacy

On Railway:

- ✅ `/data` volume persists across redeploys (conversation history survives)
- ✅ `/data` volume is isolated to this Railway project only
- ✅ Volume is never backed up externally
- ✅ Volume is never synced to GitHub
- ❌ Volume is deleted only if explicitly removed from Railway console

### If Conversation Data Leaks

If any conversation history is accidentally committed to git:

1. **Immediately force-push** to remove it from history (only acceptable use of force-push)
2. **Rotate secrets** on Railway (assume tokens may be exposed)
3. **Update memory** with what happened and how to prevent it

### Operator Responsibility

This is a **trust boundary**. The operator (you) are responsible for:

- Never copying conversation data into tickets, docs, or shared systems
- Never pasting settler messages into GitHub issues
- Treating `/data` as confidential
- Reviewing code changes that touch conversation/memory systems
- Ensuring CI/CD logs don't expose `/data` contents

---

**Updated**: 2026-04-26
**Status**: Enforced architecturally + this document
