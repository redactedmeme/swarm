import os

# ── Token mints ────────────────────────────────────────────────────────────────
TOKEN_MINT = os.environ.get(
    'TOKEN_MINT',
    '9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM',
)
SOL_MINT = 'So11111111111111111111111111111111111111112'

# When this is true the bot executes ONE swap on the first quote regardless
# of profit (used to validate the end-to-end execution pipeline on-chain).
FORCE_FIRST_SWAP = os.environ.get('FORCE_FIRST_SWAP', 'false').lower() == 'true'

# ── DEX pool addresses ────────────────────────────────────────────────────────
# Primary venue for price discovery and execution
RAYDIUM_POOL_ID = os.environ.get(
    'RAYDIUM_POOL_ID',
    '14qc563Gd2V4nKhoK6Yoj8gYEgPa8JmadLfh45czFWJ1',  # REDACTED/SOL Raydium CPMM
)

# Secondary venue — Meteora DLMM (0.25% fee); price via DexScreener, execution via Jupiter.
METEORA_POOL_ID = os.environ.get(
    'METEORA_POOL_ID',
    'HvE4Dk891ypuFSTT249gDYXinr9cboRxvKXzbXPFUvMQ',  # REDACTED/SOL Meteora DLMM
)

# Minimum price discrepancy between pools to route to the cheaper venue (bps).
# 75bps = 0.75% — covers Meteora 0.25% fee + Raydium 0.25% fee + slippage buffer.
ARB_MIN_DISCREPANCY_BPS = int(os.environ.get('ARB_MIN_DISCREPANCY_BPS', '75'))

# ── API endpoints ──────────────────────────────────────────────────────────────
JUPITER_QUOTE = 'https://lite-api.jup.ag/swap/v1/quote'
JUPITER_SWAP  = 'https://lite-api.jup.ag/swap/v1/swap'
JITO_URL      = 'https://mainnet.block-engine.jito.wtf/api/v1/bundles'
HELIUS_RPC    = 'https://mainnet.helius-rpc.com/?api-key={key}'

# Jito tip accounts (round-robin one per bundle)
JITO_TIP_ACCOUNTS = [
    '96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5',
    'HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe',
    'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY',
    'ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49',
]

# ── Execution parameters (all overridable via Railway env vars) ───────────────
POLL_INTERVAL     = int(os.environ.get('POLL_INTERVAL',     '6'))    # faster polling for volume capture
PROBE_SOL         = float(os.environ.get('PROBE_SOL',       '0.03'))
MAX_TRADE_SOL     = float(os.environ.get('MAX_TRADE_SOL',   '2.5'))  # much larger trades
SLIPPAGE_BPS      = int(os.environ.get('SLIPPAGE_BPS',      '250'))  # allow more slippage for HF trading
JITO_TIP_LAMPORTS        = int(os.environ.get('JITO_TIP_LAMPORTS',        '1000'))    # 0.000001 SOL
COMPUTE_UNIT_LIMIT       = int(os.environ.get('COMPUTE_UNIT_LIMIT',       '120000'))
COMPUTE_UNIT_PRICE_MICRO = int(os.environ.get('COMPUTE_UNIT_PRICE_MICRO', '1000'))   # micro-lamports per CU

# ── AMM / inventory rebalancing ───────────────────────────────────────────────
# Target fraction of total portfolio value to hold in TOKEN (0.5 = 50/50).
TARGET_RATIO = float(os.environ.get('TARGET_RATIO', '0.50'))
# Only rebalance when the actual ratio deviates by more than this fraction.
# REDUCED from 0.03 (3%) to 0.015 (1.5%) for more frequent rebalancing.
# With SOL volatility, this still filters out noise but catches real imbalance.
# NOTE: Better to switch to USDC pair to avoid volatile baseline.
REBALANCE_TOLERANCE = float(os.environ.get('REBALANCE_TOLERANCE', '0.015'))
# Minimum SOL value of a rebalance trade (avoid dust trades).
MIN_TRADE_SOL    = float(os.environ.get('MIN_TRADE_SOL',    '0.0005'))
# Seconds to wait after a trade before checking balance again (tx confirmation time).
# REDUCED from 120 to 25s to allow ~2-3 trades per hour vs ~1 per hour.
TRADE_COOLDOWN   = int(os.environ.get('TRADE_COOLDOWN',   '25'))
# Token decimals — confirmed on-chain via getTokenAccountsByOwner (decimals=9).
TOKEN_DECIMALS = int(os.environ.get('TOKEN_DECIMALS', '9'))

# ── Risk management ────────────────────────────────────────────────────────────
MAX_CONSEC_FAILS   = int(os.environ.get('MAX_CONSEC_FAILS',    '8'))    # allow more failures in HF mode
PAUSE_SECONDS      = int(os.environ.get('PAUSE_SECONDS',       '90'))
DAILY_LOSS_CAP_SOL = float(os.environ.get('DAILY_LOSS_CAP_SOL', '15.0')) # higher cap for larger trades

# ── Volume-aware trading (NEW) ──────────────────────────────────────────────────
# Target percentage of market volume to capture per trading window.
TARGET_VOLUME_SHARE = float(os.environ.get('TARGET_VOLUME_SHARE', '0.22'))  # 22%

# Minimum 1h volume threshold to enable volume-capture trading (USD).
# If market 1h volume < this, skip volume-capture trades (too thin).
VOLUME_THRESHOLD_USD = float(os.environ.get('VOLUME_THRESHOLD_USD', '5000.0'))

# DexScreener polling interval for volume updates (seconds).
VOLUME_UPDATE_INTERVAL = int(os.environ.get('VOLUME_UPDATE_INTERVAL', '30'))

# Trade cooldown after a volume-capture trade (seconds).
# REDUCED from 18 to 12 to allow more frequent volume-capture trades.
VOLUME_TRADE_COOLDOWN = int(os.environ.get('VOLUME_TRADE_COOLDOWN', '12'))

# ── Phase control ──────────────────────────────────────────────────────────────
EXECUTE_TRADES = os.environ.get('EXECUTE_TRADES', 'false').lower() == 'true'

# ── Virtual concentrated liquidity (CLMM/DLMM emulation) ──────────────────────
# STRATEGY_MODE controls the rebalancing logic:
#   inventory      — original full-range CPMM behavior (default, fully backward-compat)
#   virtual_clmm   — emulates Raydium CLMM: rebalance on range exit, tighter quotes inside range
#   virtual_dlmm   — emulates Meteora DLMM: uses bin-step geometry for range boundaries
STRATEGY_MODE = os.environ.get('STRATEGY_MODE', 'inventory')

# Total virtual range width in basis points (bps).
# 2000 bps = ±1% around center price. Narrower → more frequent rebalances + higher edge per trade.
# REDUCED from 4000 (±2%) to 2500 (±1.25%) for SOL pair (volatile baseline).
# This is still wide but tighter than before — reduces false exits from pure price noise.
VIRTUAL_RANGE_BPS = int(os.environ.get('VIRTUAL_RANGE_BPS', '2500'))

# DLMM bin step in basis points (0.25% = 25 bps is the Meteora default).
VIRTUAL_BIN_STEP_BPS = int(os.environ.get('VIRTUAL_BIN_STEP_BPS', '25'))

# Liquidity distribution strategy inside the virtual range:
#   spot    — even distribution (safe default, like Meteora DLMM Spot)
#   curve   — bell-curve concentration near current price (max efficiency, lower slippage mid-range)
#   bidask  — more liquidity at range edges (Ping-Pong / volatility capture)
VIRTUAL_STRATEGY = os.environ.get('VIRTUAL_STRATEGY', 'spot')

# Re-center the virtual position after every rebalance trade.
REBALANCE_ON_RANGE_EXIT = os.environ.get('REBALANCE_ON_RANGE_EXIT', 'true').lower() == 'true'

# ── Env ────────────────────────────────────────────────────────────────────────
HELIUS_KEY  = os.environ.get('HELIUS_API_KEY', '')
REDIS_URL   = os.environ.get('REDIS_URL', 'redis://localhost:6379')
PRIVATE_KEY = os.environ.get('SOLANA_PRIVATE_KEY', '')

SOL_LAMPORTS = 1_000_000_000
