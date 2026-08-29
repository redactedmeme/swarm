"""
circuit_breaker.py — risk management for the arb keeper.

Opens the circuit (halts trading) when:
  - Too many consecutive failures (temporary cooldown)
  - Daily loss cap exceeded (halt until UTC midnight)
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import deque

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

        # ── Volatility tracking (10-minute window) ──────────────────────────────
        self.price_history: deque = deque(maxlen=600)  # Keep 10min of price samples
        self.volatility_paused_until: Optional[datetime] = None

        # ── Position exposure limits ────────────────────────────────────────────
        self.max_token_exposure_pct = 0.65  # Never hold >65% in token
        self.last_exposure_warning_time = 0.0

        # ── Hourly volume share tracking (for monitoring 20-25% goal) ───────────
        self.hourly_volume_tracker: deque = deque(maxlen=3600)  # 1h of 1-second slots
        self.hourly_sol_traded = 0.0
        self.last_hour_reset = time.monotonic()

    @staticmethod
    def _today_utc() -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def update_price_sample(self, price: float):
        """Record a price sample for volatility tracking."""
        self.price_history.append((time.monotonic(), price))

    def check_volatility_safe(self) -> bool:
        """
        Check if price volatility is within safe limits.
        Returns False (unsafe) if price moved >12% in last 10 minutes.
        """
        if len(self.price_history) < 2:
            return True  # Not enough data yet

        now = time.monotonic()
        oldest_time, oldest_price = self.price_history[0]
        _, latest_price = self.price_history[-1]

        time_window = now - oldest_time
        if time_window < 600:  # Need at least 10 minutes of data
            return True

        if oldest_price <= 0:
            return True

        pct_change = abs(latest_price - oldest_price) / oldest_price
        if pct_change > 0.12:  # 12% move
            if now - self.volatility_paused_until > 60 if self.volatility_paused_until else True:
                log.warning(
                    f'High volatility detected: {pct_change*100:.2f}% move in 10min '
                    f'(${oldest_price:.8f} → ${latest_price:.8f}) — pausing trading'
                )
                self.volatility_paused_until = now + 120  # Pause for 2 minutes
            return False
        return True

    def check_position_exposure_safe(self, sol_balance: float, token_bal_whole: float, price: float) -> bool:
        """
        Check if portfolio exposure is within limits.
        Returns False if token exposure >65% of total value.
        """
        token_value_sol = token_bal_whole * price
        total_value = sol_balance + token_value_sol

        if total_value <= 0:
            return True

        token_exposure = token_value_sol / total_value
        if token_exposure > self.max_token_exposure_pct:
            now = time.monotonic()
            if now - self.last_exposure_warning_time > 300:  # Warn every 5 minutes max
                log.warning(
                    f'Position exposure too high: token={token_exposure*100:.1f}% > '
                    f'{self.max_token_exposure_pct*100:.0f}% max — consider forced rebalance'
                )
                self.last_exposure_warning_time = now
            return False
        return True

    def record_trade_for_volume(self, sol_amount: float):
        """Record a trade amount for hourly volume tracking."""
        now = time.monotonic()

        # Reset hourly tracker if needed
        if now - self.last_hour_reset > 3600:
            self.hourly_sol_traded = 0.0
            self.last_hour_reset = now

        self.hourly_sol_traded += sol_amount

    def get_hourly_volume_stats(self) -> dict:
        """Return hourly volume share stats (for monitoring 20-25% goal)."""
        now = time.monotonic()

        # If it's been >1 hour, estimate based on current rate
        elapsed = now - self.last_hour_reset
        if elapsed >= 3600:
            # Full hour has passed, reset
            stats = {
                'hourly_sol_traded': self.hourly_sol_traded,
                'estimated_market_share': 0.0,
                'elapsed_seconds': elapsed,
            }
            self.hourly_sol_traded = 0.0
            self.last_hour_reset = now
            return stats
        else:
            # Extrapolate to full hour
            extrapolated = self.hourly_sol_traded * (3600 / max(elapsed, 1))
            return {
                'hourly_sol_traded': self.hourly_sol_traded,
                'estimated_market_share': 0.0,  # Would need market volume to calculate
                'elapsed_seconds': elapsed,
                'extrapolated_hourly': extrapolated,
            }

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
        now_mono = time.monotonic()

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

        # Volatility-based pause
        if self.volatility_paused_until and now_mono < self.volatility_paused_until:
            remaining = int(self.volatility_paused_until - now_mono)
            log.debug(f'Circuit open: volatility pause {remaining}s remaining')
            return True

        # Clear volatility pause if expired
        if self.volatility_paused_until and now_mono >= self.volatility_paused_until:
            log.info('Volatility pause expired — resuming')
            self.volatility_paused_until = None

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
        hourly_vol = self.get_hourly_volume_stats()
        return {
            'open':             self.is_open(),
            'consec_failures':  self.consec_failures,
            'daily_loss_sol':   round(self.daily_loss_sol, 6),
            'daily_profit_sol': round(self.daily_profit_sol, 6),
            'total_trades':     self.total_trades,
            'paused_until':     self.paused_until.isoformat() if self.paused_until else None,
            'volatility_paused': self.volatility_paused_until is not None,
            'hourly_sol_traded': round(hourly_vol['hourly_sol_traded'], 4),
            'max_exposure_pct':  self.max_token_exposure_pct * 100,
        }
