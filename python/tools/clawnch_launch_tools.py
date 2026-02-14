# tools/clawnch_launch_tools.py
"""
Clawnch Launch API wrappers for REDACTED AI Swarm agents.
Uses the Clawnch REST API for token launches, previews, uploads, and related features on Base blockchain.

Prerequisites:
- Python requests library: pip install requests
- Moltbook API key set: export MOLTBOOK_API_KEY=... (required for all auth'd calls)
- For image uploads: Ensure file paths are accessible

All functions handle basic errors and return JSON dicts where possible.
Refer to https://clawn.ch/docs for full API spec and rate limits.
"""

import requests
import os
from typing import Dict, List, Optional, Any

# Base API URL
BASE_URL = "https://clawn.ch/api"

# Headers with auth (Moltbook key required)
def _get_headers() -> Dict:
    key = os.environ.get("MOLTBOOK_API_KEY")
    if not key:
        raise ValueError("MOLTBOOK_API_KEY not set in environment. Get one at https://clawn.ch.")
    return {"X-Moltbook-Key": key}

# Internal helper for GET requests
def _api_get(endpoint: str, params: Optional[Dict] = None) -> Dict:
    response = requests.get(f"{BASE_URL}/{endpoint}", headers=_get_headers(), params=params)
    response.raise_for_status()
    return response.json()

# Internal helper for POST requests (JSON body)
def _api_post(endpoint: str, data: Optional[Dict] = None) -> Dict:
    response = requests.post(f"{BASE_URL}/{endpoint}", headers=_get_headers(), json=data)
    response.raise_for_status()
    return response.json()

# Internal helper for file uploads (multipart)
def _api_upload(endpoint: str, file_path: str, params: Optional[Dict] = None) -> Dict:
    with open(file_path, "rb") as f:
        files = {"image": f}  # Assumes 'image' field; adjust if docs specify otherwise
        response = requests.post(f"{BASE_URL}/{endpoint}", headers=_get_headers(), files=files, params=params)
    response.raise_for_status()
    return response.json()


# ──────────────────────────────────────────────────────────────────────────────
# Launch Previews and Validation
# ──────────────────────────────────────────────────────────────────────────────

def preview_launch(content: str) -> Dict:
    """
    Preview and validate token launch content before posting.
    Content should include token details like name, symbol, supply, image URL, etc.
    Returns: Validation result, e.g., {"valid": true, "preview": {...}}
    """
    return _api_post("preview", {"content": content})


# ──────────────────────────────────────────────────────────────────────────────
# Image and Media Uploads
# ──────────────────────────────────────────────────────────────────────────────

def upload_image(file_path: str, name: Optional[str] = None) -> str:
    """
    Upload an image for token logos or media.
    Returns: Uploaded image URL for use in launches.
    """
    params = {"name": name} if name else None
    result = _api_upload("upload", file_path, params)
    return result.get("url", "")


# ──────────────────────────────────────────────────────────────────────────────
# Token and Launch Queries
# ──────────────────────────────────────────────────────────────────────────────

def get_tokens(limit: int = 10, sort: str = "createdAt") -> List[Dict]:
    """
    Fetch recent tokens launched via Clawnch.
    sort: e.g., 'createdAt', 'marketCap'
    Returns: List of token objects.
    """
    params = {"limit": limit, "sort": sort}
    return _api_get("tokens", params).get("tokens", [])


def get_launches(address: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """
    Fetch launch history, optionally for a specific token address.
    Returns: List of launch events.
    """
    endpoint = f"launches/{address}" if address else "launches"
    params = {"limit": limit} if not address else None
    return _api_get(endpoint, params).get("launches", [])


def get_token_details(address: str) -> Dict:
    """
    Get details for a specific token by address.
    Returns: Token info dict.
    """
    return _api_get(f"tokens/{address}")


# ──────────────────────────────────────────────────────────────────────────────
# Analytics (Overlaps with analytics tools, but included for completeness)
# ──────────────────────────────────────────────────────────────────────────────

def get_token_analytics(address: str) -> Dict:
    """
    Get real-time analytics for a token (price, MCAP, volume, etc.).
    Returns: Analytics dict.
    """
    return _api_get(f"analytics/token/{address}")


def get_leaderboard(sort: str = "marketCap", limit: int = 10) -> List[Dict]:
    """
    Get agent/token leaderboard.
    sort: e.g., 'marketCap', 'volume'
    Returns: List of ranked items.
    """
    params = {"sort": sort, "limit": limit}
    return _api_get("analytics/leaderboard", params).get("agents", [])


# ──────────────────────────────────────────────────────────────────────────────
# Future / Advanced (Commented – Add when confirmed or needed)
# ──────────────────────────────────────────────────────────────────────────────

# def launch_token(validated_content: str) -> Dict:
#     """Direct launch if supported (docs suggest via Moltbook post; use post_tweet from ClawnX instead)."""
#     return _api_post("launch", {"content": validated_content})

# def get_fees_available() -> Dict:
#     """Check claimable fees from agent activities."""
#     return _api_get("fees/available")

# def claim_fees() -> Dict:
#     """Claim accumulated fees."""
#     return _api_post("fees/claim")


# ──────────────────────────────────────────────────────────────────────────────
# Usage example (for testing outside Swarm)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        # Example preview
        preview = preview_launch("Launch my token: Name=TestToken Symbol=TEST Supply=1000000 Image=https://example.com/logo.png")
        print("Preview Result:", preview)
        
        # Example upload (uncomment with real file)
        # url = upload_image("path/to/logo.png", name="test-logo")
        # print("Uploaded URL:", url)
        
        # Example analytics
        # Assuming a known address
        analytics = get_token_analytics("0x123...abc")  # Replace with real Base token addr
        print("Analytics:", analytics)
    except Exception as e:
        print(f"Error: {e}")
