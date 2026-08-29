"""
volume_feed.py — Real-time volume tracking via DexScreener API.

Polls DexScreener for 5m and 1h volume rates, enabling dynamic trade sizing
and volume-capture decision logic.
"""

import logging
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class VolumeSample:
    """Snapshot of volume metrics at a point in time."""
    volume_5m_usd: float
    volume_1h_usd: float
    volume_24h_usd: float
    price_usd: float
    timestamp: float = field(default_factory=time.time)

    def is_stale(self, max_age_seconds: int = 120) -> bool:
        """Check if this sample is older than max_age_seconds."""
        return (time.time() - self.timestamp) > max_age_seconds


class VolumeFeed:
    """
    Fetches real-time volume data from DexScreener API for a Solana pair.

    Exposes rolling 5m/1h volume rates for volume-aware trade sizing.
    """

    def __init__(self, pair_address: str, polling_interval: int = 30):
        """
        Initialize VolumeFeed.

        Args:
            pair_address: Solana pair address (e.g., "14qc563Gd2V4nKhoK6Yoj8gYEgPa8JmadLfh45czFWJ1")
            polling_interval: Seconds between DexScreener API calls (default: 30s)
        """
        self.pair_address = pair_address.replace("-", "").lower()
        self.polling_interval = polling_interval
        self.last_update_time = 0.0
        self.latest_sample: Optional[VolumeSample] = None
        self.api_failures = 0
        self.max_api_failures = 5

    def update(self) -> bool:
        """
        Fetch latest volume data from DexScreener.

        Returns True if update succeeded, False otherwise.
        Only updates if polling_interval seconds have passed since last update.
        """
        now = time.time()
        if now - self.last_update_time < self.polling_interval:
            return True  # No update needed yet

        try:
            url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{self.pair_address}"
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            # DexScreener returns { pairs: [...] }
            if not data.get('pairs') or len(data['pairs']) == 0:
                log.warning(f"No pair data from DexScreener for {self.pair_address}")
                self.api_failures += 1
                return False

            pair = data['pairs'][0]
            volume = pair.get('volume', {})

            # Extract volume metrics (DexScreener provides: m5, h1, h24)
            vol_5m = float(volume.get('m5') or 0)
            vol_1h = float(volume.get('h1') or 0)
            vol_24h = float(volume.get('h24') or 0)
            price_usd = float(pair.get('priceUsd') or 0)

            self.latest_sample = VolumeSample(
                volume_5m_usd=vol_5m,
                volume_1h_usd=vol_1h,
                volume_24h_usd=vol_24h,
                price_usd=price_usd,
            )
            self.last_update_time = now
            self.api_failures = 0  # Reset on success

            log.debug(
                f"[VolumeFeed] Updated: 5m=${vol_5m:.0f} 1h=${vol_1h:.0f} 24h=${vol_24h:.0f} "
                f"price=${price_usd:.6f}"
            )
            return True

        except requests.exceptions.RequestException as e:
            log.warning(f"[VolumeFeed] API error: {e}")
            self.api_failures += 1
            if self.api_failures >= self.max_api_failures:
                log.error(
                    f"[VolumeFeed] {self.api_failures} consecutive API failures — "
                    "check DexScreener API status and pair address"
                )
            return False

    def get_volume_rate_1h(self) -> float:
        """Return the latest 1h volume in USD, or 0 if no data."""
        return self.latest_sample.volume_1h_usd if self.latest_sample else 0.0

    def get_volume_rate_5m(self) -> float:
        """Return the latest 5m volume in USD, or 0 if no data."""
        return self.latest_sample.volume_5m_usd if self.latest_sample else 0.0

    def get_volume_rate_24h(self) -> float:
        """Return the latest 24h volume in USD, or 0 if no data."""
        return self.latest_sample.volume_24h_usd if self.latest_sample else 0.0

    def get_latest_price_usd(self) -> float:
        """Return the latest price in USD from DexScreener, or 0 if no data."""
        return self.latest_sample.price_usd if self.latest_sample else 0.0

    def is_healthy(self) -> bool:
        """Check if feed has recent data (not stale)."""
        if not self.latest_sample:
            return False
        return not self.latest_sample.is_stale(max_age_seconds=120)

    def describe(self) -> str:
        """Return a human-readable status string."""
        if not self.latest_sample:
            return "[VolumeFeed] No data yet"
        age_s = time.time() - self.latest_sample.timestamp
        stale_warning = " (STALE)" if age_s > 120 else ""
        return (
            f"[VolumeFeed] 5m=${self.latest_sample.volume_5m_usd:.0f} "
            f"1h=${self.latest_sample.volume_1h_usd:.0f} "
            f"(age={age_s:.0f}s){stale_warning}"
        )
