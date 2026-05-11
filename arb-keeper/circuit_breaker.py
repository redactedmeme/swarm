"""
circuit_breaker.py — risk management for the arb keeper.

Opens the circuit (halts trading) when:
  - Too many consecutive failures (temporary cooldown)
  - Daily loss cap exceeded (halt until UTC midnight)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import config

log = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self):
        self.consec_failures:  int   = 0
        self.daily_loss_sol:   float = 0.0
        self.daily_profit_sol: float = 0.0
        self.total_trades:     int   = 0
        self.paused_until: Optional[datetime] = None
        self._day_start: datetime = self._today_utc()

    @staticmethod
    def _today_utc() -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _reset_day_if_needed(self):
        today = self._today_utc()
        if today > self._day_start:
            log.info(f'New UTC day — resetting daily loss counter (was {self.daily_loss_sol:.4f} SOL)')
            self.daily_loss_sol  = 0.0
            self.daily_profit_sol = 0.0
            self._day_start = today

    def is_open(self) -> bool:
        """Returns True when trading should be HALTED."""
        self._reset_day_if_needed()

        now = datetime.now(timezone.utc)

        # Temporary pause after consecutive failures
        if self.paused_until and now < self.paused_until:
            remaining = int((self.paused_until - now).total_seconds())
            log.debug(f'Circuit open: cooldown {remaining}s remaining')
            return True

        # Clear the pause once expired
        if self.paused_until and now >= self.paused_until:
            log.info('Circuit cooldown expired — resuming')
            self.paused_until = None
            self.consec_failures = 0

        # Daily loss cap
        if self.daily_loss_sol >= config.DAILY_LOSS_CAP_SOL:
            midnight = self._today_utc() + timedelta(days=1)
            log.warning(
                f'Circuit open: daily loss {self.daily_loss_sol:.4f} SOL >= cap '
                f'{config.DAILY_LOSS_CAP_SOL} SOL — halted until {midnight.isoformat()}'
            )
            return True

        return False

    def record_success(self, profit_sol: float):
        self.consec_failures = 0
        self.daily_profit_sol += profit_sol
        self.total_trades += 1
        log.info(
            f'Trade #{self.total_trades} success: +{profit_sol*1000:.4f} mSOL | '
            f'day P&L: +{self.daily_profit_sol*1000:.2f} mSOL'
        )

    def record_failure(self, loss_sol: float = 0.0):
        self.consec_failures += 1
        if loss_sol > 0:
            self.daily_loss_sol += loss_sol
        self.total_trades += 1

        log.warning(
            f'Trade failure #{self.consec_failures} (loss {loss_sol:.5f} SOL) | '
            f'day loss: {self.daily_loss_sol:.5f} SOL'
        )

        if self.consec_failures >= config.MAX_CONSEC_FAILS:
            self.paused_until = datetime.now(timezone.utc) + timedelta(seconds=config.PAUSE_SECONDS)
            log.warning(
                f'Circuit opened after {self.consec_failures} consecutive failures — '
                f'cooling down for {config.PAUSE_SECONDS}s'
            )

    def status(self) -> dict:
        return {
            'open':             self.is_open(),
            'consec_failures':  self.consec_failures,
            'daily_loss_sol':   round(self.daily_loss_sol, 6),
            'daily_profit_sol': round(self.daily_profit_sol, 6),
            'total_trades':     self.total_trades,
            'paused_until':     self.paused_until.isoformat() if self.paused_until else None,
        }
