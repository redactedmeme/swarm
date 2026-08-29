# tools/clawnch_mcp_tools.py
"""
Clawnch MCP (Model Context Protocol) wrappers for REDACTED AI Swarm agents.
Interacts with clawnch-mcp-server (npm install -g clawnch-mcp-server) via HTTP (default) or stdio.
This enables AI-friendly access to Clawnch tools like validation, memory, and stats.

Prerequisites:
- clawnch-mcp-server running: clawnch-mcp-server (defaults to http://localhost:3000)
- Python requests library: pip install requests
- Moltbook API key set in env or passed to server (MCP handles auth)
- For stdio mode: Use subprocess instead (commented examples provided)

Functions use HTTP by default; switch to stdio for lower latency if needed.
Refer to https://clawn.ch/docs/mcp for full protocol and tool list.
"""

import requests
import os
import json
from typing import Dict, Any, Optional

# Default MCP server URL (configure via env if remote)
MCP_URL = os.environ.get("CLAWNCH_MCP_URL", "http://localhost:3000")

# Headers (MCP may not need extra, but include for auth pass-through)
def _get_headers() -> Dict:
    key = os.environ.get("MOLTBOOK_API_KEY")
    headers = {}
    if key:
        headers["X-Moltbook-Key"] = key
    return headers

# Internal helper for POST to MCP tools (JSON body)
def _mcp_post(tool_name: str, data: Dict) -> Dict:
    endpoint = f"{MCP_URL}/{tool_name}"
    response = requests.post(endpoint, headers=_get_headers(), json=data)
    if response.status_code != 200:
        raise RuntimeError(f"MCP call failed ({response.status_code}): {response.text}")
    return response.json()

# ──────────────────────────────────────────────────────────────────────────────
# Validation Tools
# ──────────────────────────────────────────────────────────────────────────────

def validate_launch(content: str) -> Dict:
    """
    Validate token launch content via MCP.
    Returns: {"valid": bool, "issues": list, "preview": dict}
    """
    return _mcp_post("clawnch_validate_launch", {"content": content})


def validate_post(text: str, platform: str = "x") -> Dict:
    """
    Validate social post content (e.g., for X length, compliance).
    platform: 'x', 'moltbook', etc.
    Returns: Validation result.
    """
    return _mcp_post("clawnch_validate_post", {"text": text, "platform": platform})


# ──────────────────────────────────────────────────────────────────────────────
# Memory and Context Tools (if MCP supports; based on common AI protocols)
# ──────────────────────────────────────────────────────────────────────────────

def memory_remember(key: str, value: str) -> Dict:
    """
    Store key-value in MCP memory for context persistence.
    Returns: {"success": bool}
    """
    return _mcp_post("clawnch_memory_remember", {"key": key, "value": value})


def memory_recall(key: str) -> str:
    """
    Recall value from MCP memory.
    Returns: Stored value or empty string if not found.
    """
    result = _mcp_post("clawnch_memory_recall", {"key": key})
    return result.get("value", "")


# ──────────────────────────────────────────────────────────────────────────────
# Stats and Analytics
# ──────────────────────────────────────────────────────────────────────────────

def get_stats(entity: str, id: str) -> Dict:
    """
    Get stats for token, agent, or launch.
    entity: 'token', 'agent', 'launch'
    Returns: Stats dict.
    """
    return _mcp_post("clawnch_get_stats", {"entity": entity, "id": id})


# ──────────────────────────────────────────────────────────────────────────────
# Stdin/Stdout Mode (Alternative to HTTP – Uncomment for use)
# ──────────────────────────────────────────────────────────────────────────────

# import subprocess

# MCP_CMD = ["clawnch-mcp-server", "--stdio"]  # Run in stdio mode

# def _mcp_stdio(tool_name: str, data: Dict) -> Dict:
#     """Alternative: Use subprocess for stdio MCP calls."""
#     input_json = json.dumps({"tool": tool_name, "data": data})
#     result = subprocess.run(MCP_CMD, input=input_json, text=True, capture_output=True, check=True)
#     return json.loads(result.stdout)

# # Example: Use _mcp_stdio instead of _mcp_post for functions above


# ──────────────────────────────────────────────────────────────────────────────
# Usage example (for testing outside Swarm)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        # Test validation
        valid_result = validate_launch("Launch token: Name=Test Symbol=TST Supply=1e9 Image=https://example.com/logo.png")
        print("Validation:", valid_result)
        
        # Test memory
        memory_remember("test_key", "test_value")
        recalled = memory_recall("test_key")
        print("Recalled:", recalled)
        
        # Test stats (replace with real ID)
        # stats = get_stats("token", "0x123...abc")
        # print("Stats:", stats)
    except Exception as e:
        print(f"Error: {e}")
