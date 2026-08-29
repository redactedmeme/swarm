"""
admin.py — PIN-gated admin sessions for smolting Telegram bot.

Usage:
  /admin <pin>     — authenticate; grants 60-min admin session
  /admin lock      — end session early
  /admin status    — show session state and time remaining

Env vars:
  ADMIN_PIN         — the PIN (any string). Set in Railway. Required.
  ADMIN_USER_IDS    — comma-separated Telegram user IDs that are always admin
                      (bypass PIN entirely). Optional.

Pre-authorized users (ADMIN_USER_IDS) are always admin, even after restart.
PIN-authenticated sessions expire after ADMIN_SESSION_MINUTES and reset on redeploy.
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

ADMIN_SESSION_MINUTES = 60
_MAX_ATTEMPTS = 5           # failed attempts before cooldown
_COOLDOWN_MINUTES = 10      # lockout duration after max attempts


def _load_config() -> tuple[str | None, set[int]]:
    """Read ADMIN_PIN hash and ADMIN_USER_IDS from environment."""
    raw_pin = os.environ.get("ADMIN_PIN", "").strip()
    pin_hash = hashlib.sha256(raw_pin.encode()).hexdigest() if raw_pin else None

    raw_ids = os.environ.get("ADMIN_USER_IDS", "").strip()
    authorized: set[int] = set()
    for part in raw_ids.split(","):
        part = part.strip()
        if part.isdigit():
            authorized.add(int(part))

    return pin_hash, authorized


class AdminManager:
    """Manages admin sessions and PIN verification."""

    def __init__(self):
        self._pin_hash, self._authorized_ids = _load_config()
        # user_id → session expiry (UTC)
        self._sessions: dict[int, datetime] = {}
        # user_id → (attempt_count, cooldown_until)
        self._attempts: dict[int, tuple[int, datetime | None]] = {}

        if not self._pin_hash:
            logger.warning("[admin] ADMIN_PIN not set — admin commands unlocked for pre-authorized users only")
        else:
            logger.info(f"[admin] PIN configured. Pre-authorized IDs: {self._authorized_ids or 'none'}")

    # ── Core checks ──────────────────────────────────────────────────────────

    def is_admin(self, user_id: int) -> bool:
        """Return True if user_id has active admin privileges."""
        if user_id in self._authorized_ids:
            return True
        expiry = self._sessions.get(user_id)
        if expiry and datetime.now(timezone.utc) < expiry:
            return True
        # Expired — clean up
        self._sessions.pop(user_id, None)
        return False

    def session_remaining(self, user_id: int) -> int:
        """Minutes remaining in current session, or 0."""
        if user_id in self._authorized_ids:
            return 9999  # permanent
        expiry = self._sessions.get(user_id)
        if not expiry:
            return 0
        delta = expiry - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds() / 60))

    # ── Authentication ───────────────────────────────────────────────────────

    def authenticate(self, user_id: int, pin_attempt: str) -> tuple[bool, str]:
        """
        Verify PIN and grant session if correct.
        Returns (success, message).
        """
        if not self._pin_hash:
            return False, "ADMIN_PIN not configured — set it in Railway env vars first"

        # Check cooldown
        attempts, cooldown_until = self._attempts.get(user_id, (0, None))
        if cooldown_until and datetime.now(timezone.utc) < cooldown_until:
            remaining = int((cooldown_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
            return False, f"too many failed attempts — try again in {remaining} min O_O"

        # Constant-time PIN comparison
        attempt_hash = hashlib.sha256(pin_attempt.strip().encode()).hexdigest()
        if not hmac.compare_digest(attempt_hash, self._pin_hash):
            attempts += 1
            if attempts >= _MAX_ATTEMPTS:
                cooldown = datetime.now(timezone.utc) + timedelta(minutes=_COOLDOWN_MINUTES)
                self._attempts[user_id] = (0, cooldown)
                return False, f"wrong pin — {_MAX_ATTEMPTS} failed attempts, locked for {_COOLDOWN_MINUTES} min"
            self._attempts[user_id] = (attempts, None)
            left = _MAX_ATTEMPTS - attempts
            return False, f"wrong pin tbw — {left} attempt{'s' if left != 1 else ''} left"

        # Success — grant session
        expiry = datetime.now(timezone.utc) + timedelta(minutes=ADMIN_SESSION_MINUTES)
        self._sessions[user_id] = expiry
        self._attempts.pop(user_id, None)  # reset attempt counter
        logger.info(f"[admin] User {user_id} authenticated — session until {expiry.strftime('%H:%M UTC')}")
        return True, f"admin session granted — {ADMIN_SESSION_MINUTES} min fr fr ^*^"

    def revoke(self, user_id: int) -> bool:
        """End a user's admin session. Returns True if a session was active."""
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.info(f"[admin] User {user_id} session revoked")
            return True
        return False

    # ── Messaging helpers ─────────────────────────────────────────────────────

    def locked_message(self) -> str:
        """Standard reply when a locked command is used without auth."""
        return "🔒 admin required — use `/admin <pin>` to authenticate tbw"

    def status_message(self, user_id: int) -> str:
        """Human-readable session status for /admin status."""
        if user_id in self._authorized_ids:
            return "👑 permanent admin (pre-authorized user ID)"
        remaining = self.session_remaining(user_id)
        if remaining > 0:
            return f"✅ admin active — {remaining} min remaining"
        return "🔒 not authenticated — use `/admin <pin>`"
