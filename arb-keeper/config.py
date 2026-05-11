import os

# ── Token mints ────────────────────────────────────────────────────────────────
# TOKEN_MINT can be overridden via env (e.g. TOKEN_MINT=USDC mint for pipeline tests)
TOKEN_MINT = os.environ.get(
    'TOKEN_MINT',
    '9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM',  # default: REDACTED liquidity
)
SOL_MINT   = 'So11111111111111111111111111111111111111112'        # Wrapped SOL

# When this is true the bot executes ONE swap on the first quote regardless
# of profit (used to validate the end-to-end execution pipeline on-chain).
FORCE_FIRST_SWAP = os.environ.get('FORCE_FIRST_SWAP', 'false').lower() == 'true'

# ── API endpoints ──────────────────────────────────────────────────────────────
# lite-api is the free, public tier (rate-limited); api.jup.ag requires an API key.
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
POLL_INTERVAL      = int(os.environ.get('POLL_INTERVAL',     '5'))
PROBE_SOL          = float(os.environ.get('PROBE_SOL',       '0.005'))  # small probe
MIN_PROFIT_SOL     = float(os.environ.get('MIN_PROFIT_SOL',  '0.001'))  # 1 mSOL minimum
MAX_TRADE_SOL      = float(os.environ.get('MAX_TRADE_SOL',   '0.005'))  # 0.005 SOL test size
SLIPPAGE_BPS       = int(os.environ.get('SLIPPAGE_BPS',      '25'))     # 0.25% — tight for arb
JITO_TIP_LAMPORTS  = int(os.environ.get('JITO_TIP_LAMPORTS', '25000'))  # ~0.000025 SOL

# ── Risk management ────────────────────────────────────────────────────────────
MAX_CONSEC_FAILS    = int(os.environ.get('MAX_CONSEC_FAILS',    '3'))
PAUSE_SECONDS       = int(os.environ.get('PAUSE_SECONDS',       '300'))
DAILY_LOSS_CAP_SOL  = float(os.environ.get('DAILY_LOSS_CAP_SOL', '0.05'))  # tighter cap for testing

# ── Phase control ──────────────────────────────────────────────────────────────
# Set EXECUTE_TRADES=false in Railway env to run in detect-only (Phase 1) mode
EXECUTE_TRADES = os.environ.get('EXECUTE_TRADES', 'false').lower() == 'true'

# ── Env ────────────────────────────────────────────────────────────────────────
HELIUS_KEY   = os.environ.get('HELIUS_API_KEY', '')
REDIS_URL    = os.environ.get('REDIS_URL', 'redis://localhost:6379')
PRIVATE_KEY  = os.environ.get('SOLANA_PRIVATE_KEY', '')   # base58 or hex 64-byte keypair

SOL_LAMPORTS = 1_000_000_000  # lamports per SOL
