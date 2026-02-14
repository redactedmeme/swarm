# tools/clawnx_tools.py
"""
ClawnX CLI wrappers for Swarm agents.
Uses the clawnch CLI (npm install -g clawnch) to interact with official X API via Clawnch.

Prerequisites:
- Node.js installed
- clawnch CLI: npm install -g clawnch
- Moltbook API key set (for Clawnch auth / subsidies): export MOLTBOOK_API_KEY=...
- Optional: X API credentials if not using Clawnch proxy auth

All commands assume --json output for machine-readable results.
"""

import subprocess
import json
import os
from typing import Dict, List, Optional, Any

# Base command prefix
CLAWNCH_CMD = ["clawnch", "x"]

# Ensure CLI is available (you can move this to setup/init if preferred)
def _check_clawnch_installed() -> None:
    try:
        subprocess.run(["clawnch", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError(
            "Clawnch CLI not found. Install with: npm install -g clawnch\n"
            "Also ensure MOLTBOOK_API_KEY is set in environment."
        )

_check_clawnch_installed()


def _run_clawnch(args: List[str], check: bool = True) -> Dict[str, Any]:
    """Internal helper: run clawnch x ... --json and parse output."""
    cmd = CLAWNCH_CMD + args + ["--json"]
    env = os.environ.copy()
    # Ensure Moltbook key is passed if set
    if "MOLTBOOK_API_KEY" in env:
        env["MOLTBOOK_API_KEY"] = env["MOLTBOOK_API_KEY"]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=check,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ClawnX command failed ({result.returncode}):\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )

    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        # Fallback for commands that might not be --json clean
        return {"raw_stdout": result.stdout.strip(), "success": True}


# ──────────────────────────────────────────────────────────────────────────────
# Tweets
# ──────────────────────────────────────────────────────────────────────────────

def post_tweet(text: str, reply_to: Optional[str] = None, quote_id: Optional[str] = None) -> Dict:
    """
    Post a new tweet (or reply/quote).
    Returns: {"id": "...", "url": "...", ...}
    """
    args = ["tweet", "post", "--text", text]
    if reply_to:
        args.extend(["--reply-to", reply_to])
    if quote_id:
        args.extend(["--quote", quote_id])
    return _run_clawnch(args)


def get_tweet(tweet_id: str) -> Dict:
    """Fetch a single tweet by ID or URL."""
    args = ["tweet", "get", tweet_id]
    return _run_clawnch(args)


def search_tweets(query: str, limit: int = 10, latest: bool = False) -> List[Dict]:
    """
    Search for tweets.
    Returns: list of tweet objects
    """
    args = ["tweet", "search", query, "--limit", str(limit)]
    if latest:
        args.append("--latest")     # assuming this flag exists (common pattern)
    result = _run_clawnch(args)
    return result.get("results", result.get("tweets", []))


def post_thread(tweets: List[str]) -> Dict:
    """
    Post a thread.
    tweets: list of strings (each becomes a tweet in the thread)
    Example: post_thread(["1/3 Hello", "2/3 World", "3/3 End"])
    """
    if not tweets:
        raise ValueError("Thread cannot be empty")
    content = "|".join(tweets)
    args = ["tweet", "thread", content]
    return _run_clawnch(args)


# ──────────────────────────────────────────────────────────────────────────────
# Engagements
# ──────────────────────────────────────────────────────────────────────────────

def like_tweet(tweet_id: str) -> Dict:
    """Like a tweet."""
    args = ["like", tweet_id]
    return _run_clawnch(args)


def unlike_tweet(tweet_id: str) -> Dict:
    """Unlike a tweet (assuming inverse command supported)."""
    args = ["unlike", tweet_id]     # may be "unlike" or "like --remove"
    return _run_clawnch(args)


def retweet(tweet_id: str) -> Dict:
    """Retweet a post."""
    args = ["retweet", tweet_id]
    return _run_clawnch(args)


def unretweet(tweet_id: str) -> Dict:
    """Undo retweet."""
    args = ["unretweet", tweet_id]  # assuming supported
    return _run_clawnch(args)


def follow_user(username: str) -> Dict:
    """Follow a user by @handle or user ID."""
    args = ["follow", username]
    return _run_clawnch(args)


def unfollow_user(username: str) -> Dict:
    """Unfollow a user."""
    args = ["unfollow", username]
    return _run_clawnch(args)


# ──────────────────────────────────────────────────────────────────────────────
# Users & Profiles
# ──────────────────────────────────────────────────────────────────────────────

def get_user(username: str) -> Dict:
    """Get user profile by @handle."""
    args = ["user", "get", username]
    return _run_clawnch(args)


def get_current_user() -> Dict:
    """Get profile of the authenticated account."""
    args = ["me", "profile"]
    return _run_clawnch(args)


def get_home_timeline(limit: int = 20) -> List[Dict]:
    """Get home timeline (assuming supported)."""
    args = ["me", "home", "--limit", str(limit)]
    result = _run_clawnch(args)
    return result.get("tweets", [])


# ──────────────────────────────────────────────────────────────────────────────
# Future / Probable commands (commented – add when confirmed)
# ──────────────────────────────────────────────────────────────────────────────

# def send_dm(user: str, text: str) -> Dict:
#     args = ["dm", "send", "--to", user, "--text", text]
#     return _run_clawnch(args)

# def upload_media(file_path: str) -> str:
#     """Returns media_id to use in tweets."""
#     args = ["media", "upload", file_path]
#     result = _run_clawnch(args)
#     return result.get("media_id")

# def get_user_timeline(username: str, limit: int = 20) -> List[Dict]:
#     args = ["user", "timeline", username, "--limit", str(limit)]
#     result = _run_clawnch(args)
#     return result.get("tweets", [])


# ──────────────────────────────────────────────────────────────────────────────
# Usage example (for testing outside Swarm)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        print("Testing post_tweet simulation (dry-run only)")
        # tweet = post_tweet("Test from Swarm agent via ClawnX 🦞")
        # print(tweet)
        
        results = search_tweets("Clawnch AI agents", limit=5)
        print(f"Found {len(results)} tweets.")
    except Exception as e:
        print(f"Error: {e}")
