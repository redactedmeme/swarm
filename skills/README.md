# REDACTED Swarm Skills

Reusable, versioned, self-improving knowledge units for the REDACTED AI Swarm.

Skills follow [AgentSkills.io](https://agentskills.io) conventions:
- Markdown documentation
- Embedded executable Python
- Versioned, auto-improved on repeated successful use

Skills are created by the learning loop after complex conversation trajectories
and stored in `/data/skills/` at runtime. The files in this directory are
committed example / seed skills that ship with the repo.

## Index

| Skill | Tags | Description |
|---|---|---|
| [hermes_deploy_check.md](hermes_deploy_check.md) | deploy, hermes, railway | Check Railway service status and recent logs via Hermes |
| [memory_synthesis.md](memory_synthesis.md) | memory, recall, synthesis | Synthesize facts + vault entries into a coherent context brief |
| [emotional_escalation_response.md](emotional_escalation_response.md) | affect, emotional, de-escalation | Respond to escalating emotional trajectories with grounded warmth |
