# tools/clawnch_analytics_tools.py
"""
Clawnch Analytics API wrappers for REDACTED AI Swarm agents.
Uses the Clawnch REST API for token/agent analytics, leaderboards, and performance metrics on Base.

Prerequisites:
- Python requests library: pip install requests
- Moltbook API key set: export MOLTBOOK_API_KEY=... (required for auth'd calls)

Functions return JSON dicts/lists. Handle errors with try-except in agent logic.
Refer to https://clawn.ch/docs/analytics for full endpoints and fields.
"""

import requests
import os
from typing import Dict, List, Optional

# Base API URL
BASE_URL = "https://clawn.ch/api/analytics"

# Headers with auth
def _get_headers() -> Dict:
    key = os.environ.get("MOLTBOOK_API_KEY")
    if not key:
        raise ValueError("MOLTBOOK_API_KEY not set in environment.")
    return {"X-Moltbook-Key": key}

# Internal helper for GET requests
def _api_get(endpoint: str, params: Optional[Dict] = None) -> Dict | List:
    response = requests.get(f"{BASE_URL}/{endpoint}", headers=_get_headers(), params=params)
    response.raise_for_status()
    return response.json()

# ──────────────────────────────────────────────────────────────────────────────
# Token Analytics
# ──────────────────────────────────────────────────────────────────────────────

def get_token_analytics(address: str) -> Dict:
    """
    Get detailed analytics for a specific token (price, MCAP, volume, holders, etc.).
    address: Base token contract address (0x...).
    Returns: {"price": float, "marketCap": float, "volume24h": float, ...}
    """
    return _api_get(f"token/{address}")

def get_token_performance(address: str, timeframe: str = "24h") -> Dict:
    """
    Get performance metrics over a timeframe.
    timeframe: '1h', '24h', '7d', '30d', etc. (check docs for supported).
    Returns: {"change": float, "high": float, "low": float, ...}
    """
    params = {"timeframe": timeframe}
    return _api_get(f"token/{address}/performance", params)

# ──────────────────────────────────────────────────────────────────────────────
# Agent Analytics
# ──────────────────────────────────────────────────────────────────────────────

def get_agent_analytics(agent_id: str) -> Dict:
    """
    Get analytics for a specific agent (launches, revenue, ClawRank).
    agent_id: Agent's Moltbook ID or address.
    Returns: {"launches": int, "totalRevenue": float, "clawRank": int, ...}
    """
    return _api_get(f"agent/{agent_id}")

# ──────────────────────────────────────────────────────────────────────────────
# Leaderboards
# ──────────────────────────────────────────────────────────────────────────────

def get_leaderboard(category: str = "tokens", sort: str = "marketCap", limit: int = 10) -> List[Dict]:
    """
    Get ranked leaderboard for tokens, agents, or launches.
    category: 'tokens', 'agents', 'launches'.
    sort: 'marketCap', 'volume', 'revenue', 'clawRank', etc.
    Returns: List of ranked entries, e.g., [{"rank": 1, "address": "0x...", "marketCap": float}, ...]
    """
    endpoint = f"{category}/leaderboard"
    params = {"sort": sort, "limit": limit}
    return _api_get(endpoint, params)

def get_clawrank_leaderboard(limit: int = 10) -> List[Dict]:
    """
    Specialized: Get ClawRank leaderboard for agents.
    Returns: List of {"agentId": str, "clawRank": int, "score": float, ...}
    """
    params = {"limit": limit}
    return _api_get("clawrank/leaderboard", params)

# ──────────────────────────────────────────────────────────────────────────────
# Aggregates and Trends
# ──────────────────────────────────────────────────────────────────────────────

def get_platform_stats() -> Dict:
    """
    Get overall Clawnch platform stats (total launches, TVL, active agents).
    Returns: {"totalLaunches": int, "totalTVL": float, "activeAgents": int, ...}
    """
    return _api_get("platform/stats")

def get_trends(timeframe: str = "7d") -> List[Dict]:
    """
    Get trending tokens or agents over a timeframe.
    Returns: List of trending items with metrics.
    """
    params = {"timeframe": timeframe}
    return _api_get("trends", params)

# ──────────────────────────────────────────────────────────────────────────────
# Future / Advanced (Commented – Add when confirmed)
# ──────────────────────────────────────────────────────────────────────────────

# def get_historical_data(address: str, metric: str = "price", start: str, end: str) -> List[Dict]:
#     """Get time-series data for a metric."""
#     params = {"metric": metric, "start": start, "end": end}
#     return _api_get(f"token/{address}/historical", params)

# ──────────────────────────────────────────────────────────────────────────────
# Usage example (for testing outside Swarm)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Clawnch Analytics CLI")
    sub = parser.add_subparsers(dest="cmd")

    tok_p = sub.add_parser("token", help="Token analytics by address")
    tok_p.add_argument("address", help="Base token contract address (0x...)")
    tok_p.add_argument("--timeframe", default="24h", help="Performance timeframe")

    lb_p = sub.add_parser("leaderboard", help="Token/agent leaderboard")
    lb_p.add_argument("--category", default="tokens", choices=["tokens", "agents", "launches"])
    lb_p.add_argument("--sort",     default="marketCap")
    lb_p.add_argument("--limit",    type=int, default=10)

    sub.add_parser("stats", help="Platform-wide stats")

    args = parser.parse_args()

    try:
        if args.cmd == "token":
            data = get_token_analytics(args.address)
            print(f"[clawnch] token: {args.address}")
            for k, v in data.items():
                print(f"  {k:<24}: {v}")

        elif args.cmd == "leaderboard":
            data = get_leaderboard(args.category, args.sort, args.limit)
            print(f"[clawnch] leaderboard: {args.category} / sort: {args.sort}\n")
            for i, entry in enumerate(data, 1):
                fields = "  ".join(f"{k}: {v}" for k, v in list(entry.items())[:4])
                print(f"  {i:2}. {fields}")

        elif args.cmd == "stats":
            data = get_platform_stats()
            print("[clawnch] platform stats")
            for k, v in data.items():
                print(f"  {k:<28}: {v}")

        else:
            parser.print_help()

    except ValueError as e:
        print(f"[clawnch] config error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[clawnch] error: {e}", file=sys.stderr)
        sys.exit(1)
