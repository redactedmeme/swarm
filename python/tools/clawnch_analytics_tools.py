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
    try:
        # Replace with real Base token address (e.g., $CLAWNCH)
        token_addr = "0x123abc...def"  # Example
        analytics = get_token_analytics(token_addr)
        print("Token Analytics:", analytics)
        
        leaderboard = get_leaderboard("tokens", "volume", 5)
        print("Top 5 by Volume:", leaderboard)
        
        platform = get_platform_stats()
        print("Platform Stats:", platform)
    except Exception as e:
        print(f"Error: {e}")
