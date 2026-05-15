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
POLL_INTERVAL     = int(os.environ.get('POLL_INTERVAL',     '30'))   # pool reads, not Jupiter polling
PROBE_SOL         = float(os.environ.get('PROBE_SOL',       '0.005'))
MAX_TRADE_SOL     = float(os.environ.get('MAX_TRADE_SOL',   '0.005'))
SLIPPAGE_BPS      = int(os.environ.get('SLIPPAGE_BPS',      '100'))  # wider for AMM rebalancing
JITO_TIP_LAMPORTS = int(os.environ.get('JITO_TIP_LAMPORTS', '25000'))

# ── AMM / inventory rebalancing ───────────────────────────────────────────────
# Target fraction of total portfolio value to hold in TOKEN (0.5 = 50/50).
TARGET_RATIO = float(os.environ.get('TARGET_RATIO', '0.50'))
# Only rebalance when the actual ratio deviates by more than this fraction.
# e.g. 0.03 means rebalance if token share drifts outside [47%, 53%].
REBALANCE_TOLERANCE = float(os.environ.get('REBALANCE_TOLERANCE', '0.03'))
# Minimum SOL value of a rebalance trade (avoid dust trades).
MIN_TRADE_SOL    = float(os.environ.get('MIN_TRADE_SOL',    '0.0005'))
# Seconds to wait after a trade before checking balance again (tx confirmation time).
TRADE_COOLDOWN   = int(os.environ.get('TRADE_COOLDOWN',   '120'))
# Token decimals — confirmed on-chain via getTokenAccountsByOwner (decimals=9).
TOKEN_DECIMALS = int(os.environ.get('TOKEN_DECIMALS', '9'))

# ── Risk management ────────────────────────────────────────────────────────────
MAX_CONSEC_FAILS   = int(os.environ.get('MAX_CONSEC_FAILS',    '3'))
PAUSE_SECONDS      = int(os.environ.get('PAUSE_SECONDS',       '300'))
DAILY_LOSS_CAP_SOL = float(os.environ.get('DAILY_LOSS_CAP_SOL', '0.05'))

# ── Phase control ──────────────────────────────────────────────────────────────
EXECUTE_TRADES = os.environ.get('EXECUTE_TRADES', 'false').lower() == 'true'

# ── Env ────────────────────────────────────────────────────────────────────────
HELIUS_KEY  = os.environ.get('HELIUS_API_KEY', '')
REDIS_URL   = os.environ.get('REDIS_URL', 'redis://localhost:6379')
PRIVATE_KEY = os.environ.get('SOLANA_PRIVATE_KEY', '')

SOL_LAMPORTS = 1_000_000_000
