"""Sliding window rate limiter for the echo handler."""

from collections import defaultdict
from time import monotonic

_windows: dict[int, list[float]] = defaultdict(list)

WINDOW_SEC    = 60
MAX_PER_WINDOW = 20  # max messages per user per 60s


def check_rate(user_id: int) -> bool:
    """Returns True if the message is allowed, False if rate-limited."""
    now = monotonic()
    window = _windows[user_id]
    # Prune expired entries
    _windows[user_id] = [t for t in window if now - t < WINDOW_SEC]
    if len(_windows[user_id]) >= MAX_PER_WINDOW:
        return False
    _windows[user_id].append(now)
    return True
