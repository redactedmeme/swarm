#!/usr/bin/env python3
"""
Stdio MCP server for REDACTED Swarm — Hermes-style FastMCP bridge (cherry-pick from Nous hermes-agent).

- Exposes agents/skills via skills_list + skills_read (local files, agentskills.io layout).
- Optionally proxies broadcast, alpha, committee, phi to the deployed HTTP MCP (Railway).

Run (from smolting-telegram-bot/):
  pip install mcp PyYAML requests
  set SWARM_MCP_HTTP_URL=https://your-service.up.railway.app
  set SWARM_API_TOKEN=...
  python swarm_mcp_stdio.py

Cursor / Claude Desktop snippet:
  "command": "python",
  "args": ["/absolute/path/to/smolting-telegram-bot/swarm_mcp_stdio.py"]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("swarm_mcp_stdio")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "Missing dependency: pip install 'mcp>=1.3' PyYAML requests",
        file=sys.stderr,
    )
    raise SystemExit(1)

import requests

# Ensure local imports (swarm_skills) resolve when cwd differs
_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

import swarm_skills  # noqa: E402


def _proxy_http_tool(name: str, arguments: dict) -> str:
    base = os.environ.get("SWARM_MCP_HTTP_URL", "").strip().rstrip("/")
    if not base:
        return json.dumps({
            "ok": False,
            "error": "Set SWARM_MCP_HTTP_URL to the smolting webhook base URL (no trailing path).",
        })
    token = os.environ.get("SWARM_API_TOKEN", "").strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(
            f"{base}/mcp/call",
            json={"name": name, "arguments": arguments or {}},
            headers=headers,
            timeout=120,
        )
        return r.text
    except requests.RequestException as e:
        return json.dumps({"ok": False, "error": str(e)})


def build_mcp() -> FastMCP:
    mcp = FastMCP(
        "redacted-swarm",
        instructions=(
            "REDACTED AI Swarm MCP. skills_list / skills_read load agentskills-style SKILL.md from "
            "agents/skills. broadcast, alpha, committee, phi forward to SWARM_MCP_HTTP_URL when set."
        ),
    )

    @mcp.tool()
    def skills_list() -> str:
        """List bundled skills (id, name, description) from agents/skills/*/SKILL.md."""
        rows = swarm_skills.list_skills()
        return json.dumps({"ok": True, "count": len(rows), "skills": rows}, indent=2)

    @mcp.tool()
    def skills_read(skill_id: str) -> str:
        """Load one skill's full SKILL.md by directory id (e.g. hermes-fastmcp, redacted-swarm-mcp)."""
        text = swarm_skills.read_skill(skill_id.strip())
        if text is None:
            return json.dumps({"ok": False, "error": f"skill not found: {skill_id!r}"})
        return json.dumps({"ok": True, "skill_id": skill_id, "content": text}, indent=2)

    @mcp.tool()
    def broadcast(text: str, chat_id: str = "", parse_mode: str = "") -> str:
        """Send a Telegram message via the remote smolting HTTP MCP (requires SWARM_MCP_HTTP_URL)."""
        args: dict = {"text": text}
        if chat_id:
            args["chat_id"] = chat_id
        if parse_mode:
            args["parse_mode"] = parse_mode
        return _proxy_http_tool("broadcast", args)

    @mcp.tool()
    def alpha(chat_id: str = "") -> str:
        """Trigger the daily alpha job on the remote bot (requires SWARM_MCP_HTTP_URL)."""
        args = {"chat_id": chat_id} if chat_id else {}
        return _proxy_http_tool("alpha", args)

    @mcp.tool()
    def committee(proposal: str, post_to_group: bool = True, chat_id: str = "") -> str:
        """Run Pattern Blue committee vote on the remote bot."""
        args: dict = {"proposal": proposal, "post_to_group": post_to_group}
        if chat_id:
            args["chat_id"] = chat_id
        return _proxy_http_tool("committee", args)

    @mcp.tool()
    def phi(
        phi: float,
        tiles: int = 0,
        vitality: float = 0.0,
        alert: str = "",
        chat_id: str = "",
    ) -> str:
        """Push Φ metric to the remote bot; optional degraded/critical alert."""
        args: dict = {"phi": phi, "tiles": tiles, "vitality": vitality}
        if alert:
            args["alert"] = alert
        if chat_id:
            args["chat_id"] = chat_id
        return _proxy_http_tool("phi", args)

    return mcp


async def _run_stdio() -> None:
    server = build_mcp()
    await server.run_stdio_async()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
