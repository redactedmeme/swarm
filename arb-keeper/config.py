import os

# ── Token mints ────────────────────────────────────────────────────────────────
TOKEN_MINT = '9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM'   # REDACTED liquidity
SOL_MINT   = 'So11111111111111111111111111111111111111112'        # Wrapped SOL

# ── API endpoints ──────────────────────────────────────────────────────────────
JUPITER_QUOTE = 'https://quote-api.jup.ag/v6/quote'
JUPITER_SWAP  = 'https://quote-api.jup.ag/v6/swap'
JITO_URL      = 'https://mainnet.block-engine.jito.wtf/api/v1/bundles'
HELIUS_RPC    = 'https://mainnet.helius-rpc.com/?api-key={key}'

# Jito tip accounts (round-robin one per bundle)
JITO_TIP_ACCOUNTS = [
    '96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5',
    'HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe',
    'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY',
    'ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49',
]

# ── Execution parameters ───────────────────────────────────────────────────────
POLL_INTERVAL      = 5        # seconds between price checks
PROBE_SOL          = 0.01     # SOL used for price probe quotes
MIN_PROFIT_SOL     = 0.0005   # minimum net profit after tip+fees to execute
MAX_TRADE_SOL      = 0.05     # maximum SOL per leg (position sizing cap)
SLIPPAGE_BPS       = 50       # 0.5% slippage tolerance
JITO_TIP_LAMPORTS  = 10_000   # ~0.00001 SOL tip — raise if bundles not landing

# ── Risk management ────────────────────────────────────────────────────────────
MAX_CONSEC_FAILS    = 3        # pause after this many consecutive failures
PAUSE_SECONDS       = 300      # 5-minute cooldown after circuit opens
DAILY_LOSS_CAP_SOL  = 0.1     # halt for the day if cumulative loss exceeds this

# ── Phase control ──────────────────────────────────────────────────────────────
# Set EXECUTE_TRADES=false in Railway env to run in detect-only (Phase 1) mode
EXECUTE_TRADES = os.environ.get('EXECUTE_TRADES', 'false').lower() == 'true'

# ── Env ────────────────────────────────────────────────────────────────────────
HELIUS_KEY   = os.environ.get('HELIUS_API_KEY', '')
REDIS_URL    = os.environ.get('REDIS_URL', 'redis://localhost:6379')
PRIVATE_KEY  = os.environ.get('SOLANA_PRIVATE_KEY', '')   # base58 or hex 64-byte keypair

SOL_LAMPORTS = 1_000_000_000  # lamports per SOL
