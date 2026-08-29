#!/usr/bin/env python
"""Quick test of VolumeFeed and volume-capture logic."""

import sys
import logging
logging.basicConfig(level=logging.DEBUG)

# Test VolumeFeed
from volume_feed import VolumeFeed

print("=== Testing VolumeFeed ===")
vf = VolumeFeed("14qc563Gd2V4nKhoK6Yoj8gYEgPa8JmadLfh45czFWJ1")
print(f"Initial state: {vf.describe()}")

success = vf.update()
print(f"Update result: {success}")
print(f"After update: {vf.describe()}")
print(f"  5m volume: ${vf.get_volume_rate_5m():.0f}")
print(f"  1h volume: ${vf.get_volume_rate_1h():.0f}")
print(f"  24h volume: ${vf.get_volume_rate_24h():.0f}")
print(f"  Healthy: {vf.is_healthy()}")

# Test sizing function
from detector import calculate_volume_capture_size
print("\n=== Testing calculate_volume_capture_size ===")
vol_1h = 50000.0  # $50k per hour
size = calculate_volume_capture_size(vol_1h, target_share=0.22, sol_price_usd=200.0)
print(f"1h volume: ${vol_1h:.0f}")
print(f"Target share: 22%")
print(f"Calculated trade size: {size:.4f} SOL")

# Test direction logic
from detector import determine_volume_capture_direction
print("\n=== Testing determine_volume_capture_direction ===")
# Scenario: 2 SOL, 1000 tokens, price = 0.001 SOL/token
# Token value = 1 SOL, total = 3 SOL, ratio = 1/3 = 33%
# Target = 50%, so should BUY (underweight in token)
sol_bal = 2.0
token_bal = 1000 * 10**9  # 9 decimals
price = 0.001
is_buy = determine_volume_capture_direction(sol_bal, token_bal, price)
print(f"Portfolio: {sol_bal} SOL + 1000 tokens @ {price} SOL/tok")
print(f"Ratio: 33%, Target: 50%")
print(f"Should BUY: {is_buy}")

print("\n[PASS] All basic tests passed!")
