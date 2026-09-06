# apps/workspace — persistent per-agent computer

A long-lived per-agent container with a real filesystem, shell and headless
Chromium (Playwright), reached over a **unix socket** (`WORKSPACE_SOCK`).
Implements §5 and §6 of [`docs/plans/grok-bot-parity.md`](../../docs/plans/grok-bot-parity.md).

**This is not `apps/exec-runner`.** exec-runner is deliberately powerless
(no network, no secrets, no persistence). This service is the opposite: network
+ persistence, so context compounds across tasks. Its containment is identity +
audit + egress allowlist, not a jail:

| Control | How |
|---|---|
| Per-agent auth | request carries `X-Swarm-Agent: <agent>` + `Authorization: Bearer <token>`; token must equal `WORKSPACE_TOKEN_<AGENT>` (via `swarm_core.security.secrets`), `hmac.compare_digest` |
| Per-agent isolation | root `data_dir()/workspace/<agent>`, browser profile `<root>/.browser-profile` — never shared. Path traversal rejected |
| Egress | `HTTPS_PROXY` → `apps/swarm-egress`, `workspace` caller in `security/egress.yaml` |
| Audit | every `/shell`, every `/browser/*`, every `/fs/write` → `swarm_core.security.audit.record`, actor = calling agent |
| Capability gate (caller-side) | `workspace.browse`; `workspace.shell` is **approval-gated** (network + persistence) |
| Untrusted content | `/browser/read` runs page text through `swarm_core.web.extract` then `promptguard.wrap_untrusted` |

## Endpoints

```
POST /fs/read      {path}                      -> {text|base64, bytes, encoding}
POST /fs/write     {path, content, append?}    -> {bytes}
POST /fs/list      {path?}                      -> {entries: [{name,type,size,mtime}]}
POST /shell        {cmd, timeout?, cwd?}        -> {stdout, stderr, exit_code, timed_out}
POST /browser/goto {url, session?}             -- SSRF-guarded
POST /browser/read {session?, max_chars?}      -- extracted + fenced
POST /browser/click|type|screenshot|session
GET  /session                                  -> {recent_commands, open_pages, disk_bytes}
GET  /health
```

## Enabling it

Off by default. On the caller (hermes): `WORKSPACE_ENABLED=true`,
`WORKSPACE_TOKEN_HERMES=<same value the workspace container gets>`. Deploy the
`workspace` service + `workspacedata` / `workspacesock` volumes
(`infra/umbrel/swarm-infra-docker-compose.yml`), and add `EGRESS_TOKEN_WORKSPACE`
to `swarm-egress`.

Hermes tools: `workspace_read`, `workspace_write`, `workspace_list`,
`workspace_shell`, `workspace_browse`
(`apps/hermes/plugins/swarm-manager/workspace_tools.py`).

## Tests

`python -m pytest apps/workspace/test_workspace.py` — fs traversal, isolation,
shell timeout, session view, and the HTTP auth/routing layer. Browser paths need
Playwright + a Chromium build and are exercised on the deployed image.
