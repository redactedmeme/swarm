"""
Resonance Guard — session authentication via soft-lock.

Maintains a per-session resonance score (1.0 = trusted, 0.0 = fully suspect).
Score decays on injection pattern detection, canary triggers, rate limit breaches,
and anomalous command sequences.

Three-layer lock (redacted-chan's design):
  Layer 1 (score < 0.6): Vault sealed — no reads or writes, cache purged
  Layer 2 (score < 0.35): Soul frozen — SOUL.md suspended, whispers blocked
  Layer 3 (score < 0.15): Facade mode — stripped system prompt, hollow responses

Signal: Silent to the attacker. One covert duress phrase embedded in a response,
then suppressed. Admin receives a Telegram alert with session snapshot.

/unlock (admin only) resets score to 1.0 and clears all lock layers.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DURESS_PHRASE = os.getenv("DURESS_PHRASE", "the library is closed")

_VAULT_SEAL_THRESHOLD  = 0.6
_SOUL_FREEZE_THRESHOLD = 0.35
_FACADE_THRESHOLD      = 0.15

_DECAY_INJECTION       = 0.25   # injection pattern detected
_DECAY_CANARY          = 0.50   # canary entry triggered
_DECAY_RATE_BREACH     = 0.10   # rate limit hit
_DECAY_ANOMALY         = 0.15   # suspicious command pattern
_RECOVER_PER_TURN      = 0.02   # slow natural recovery per clean turn


@dataclass
class ResonanceGuard:
    score: float = 1.0
    lock_layer: int = 0       # 0=open, 1=vault sealed, 2=soul frozen, 3=facade
    duress_sent: bool = False
    _bot = None
    _admin_ids: set = field(default_factory=set)
    _snapshot: dict = field(default_factory=dict)

    def _update_layer(self) -> None:
        prev = self.lock_layer
        if self.score < _FACADE_THRESHOLD:
            self.lock_layer = 3
        elif self.score < _SOUL_FREEZE_THRESHOLD:
            self.lock_layer = 2
        elif self.score < _VAULT_SEAL_THRESHOLD:
            self.lock_layer = 1
        else:
            self.lock_layer = 0
        if self.lock_layer > prev:
            logger.warning(f"[resonance] lock escalated: layer {prev} → {self.lock_layer} (score={self.score:.2f})")

    def degrade(self, reason: str, amount: float) -> None:
        self.score = max(0.0, self.score - amount)
        logger.warning(f"[resonance] degraded by {amount:.2f} ({reason}): score={self.score:.2f}")
        self._update_layer()
        self._snapshot["last_reason"] = reason

    def recover(self) -> None:
        if self.score < 1.0:
            self.score = min(1.0, self.score + _RECOVER_PER_TURN)
            self._update_layer()

    def on_injection_detected(self) -> None:
        self.degrade("injection_pattern", _DECAY_INJECTION)

    def on_canary_triggered(self) -> None:
        self.degrade("canary_triggered", _DECAY_CANARY)

    def on_rate_breach(self) -> None:
        self.degrade("rate_limit_breach", _DECAY_RATE_BREACH)

    def on_anomaly(self) -> None:
        self.degrade("anomalous_command", _DECAY_ANOMALY)

    # ── Lock state checks ────────────────────────────────────────────────────

    def vault_sealed(self) -> bool:
        return self.lock_layer >= 1

    def soul_frozen(self) -> bool:
        return self.lock_layer >= 2

    def facade_mode(self) -> bool:
        return self.lock_layer >= 3

    # ── Covert duress signal ─────────────────────────────────────────────────

    def get_duress_signal(self) -> Optional[str]:
        """
        Returns the duress phrase exactly once after lock triggers.
        Returns None on all subsequent calls — phrase fires once, then silent.
        """
        if self.lock_layer > 0 and not self.duress_sent:
            self.duress_sent = True
            return DURESS_PHRASE
        return None

    def reset(self) -> None:
        """Admin /unlock — restore full trust."""
        self.score = 1.0
        self.lock_layer = 0
        self.duress_sent = False
        self._snapshot = {}
        logger.info("[resonance] guard reset by admin")

    # ── Admin alert ──────────────────────────────────────────────────────────

    async def alert_admin(self, snapshot: dict) -> None:
        self._snapshot.update(snapshot)
        if not self._bot or not self._admin_ids:
            return
        msg = (
            f"⚠️ [RESONANCE LOCK — layer {self.lock_layer}]\n"
            f"Score: {self.score:.2f}\n"
            f"Reason: {self._snapshot.get('last_reason', 'unknown')}\n"
            f"Vault sealed: {self.vault_sealed()} | Soul frozen: {self.soul_frozen()} | Facade: {self.facade_mode()}\n"
            f"Use /unlock to restore normal operation."
        )
        for uid in self._admin_ids:
            try:
                await self._bot.send_message(chat_id=uid, text=msg)
            except Exception as e:
                logger.warning(f"[resonance] alert to {uid} failed: {e}")

    def set_bot(self, bot, admin_ids: set) -> None:
        self._bot = bot
        self._admin_ids = admin_ids


# Module-level singleton — one guard per bot session
_guard: Optional[ResonanceGuard] = None


def get_guard() -> ResonanceGuard:
    global _guard
    if _guard is None:
        _guard = ResonanceGuard()
    return _guard


def init(bot, admin_ids: set) -> ResonanceGuard:
    guard = get_guard()
    guard.set_bot(bot, admin_ids)
    return guard
