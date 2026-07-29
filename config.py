"""
Central configuration for the bot.

IMPORTANT: PAPER_MODE defaults to True. Do not flip it to False until
you've run this in paper mode for a meaningful stretch of time and are
comfortable with the results. See README.md.
"""

import os

# ── MODE ──────────────────────────────────────────────────────────────
# True  = simulate trades against real live prices, no real money moves
# False = send real swaps through Jupiter using a real wallet keypair
PAPER_MODE = True

# ── SOLANA / JUPITER ─────────────────────────────────────────────────
SOLANA_RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
JUPITER_QUOTE_API = "https://lite-api.jup.ag/swap/v1/quote"
JUPITER_SWAP_API = "https://lite-api.jup.ag/swap/v1/swap"

# Only required if PAPER_MODE = False. Load from an env var — never hardcode a key.
WALLET_PRIVATE_KEY = os.environ.get("SOLANA_PRIVATE_KEY", "")

# Base asset the bot trades from/to (SOL by default)
BASE_MINT = "So11111111111111111111111111111111111111112"  # wrapped SOL

# ── WATCHLIST: "OG" / smart-money wallets to monitor on-chain ──────────
# Add Solana wallet addresses you consider worth following.
# The bot watches these for new token buys as a corroborating signal —
# it does NOT trust X sentiment alone.
OG_WALLETS = [
    # "Address1...",
    # "Address2...",
]

# How many of your watched wallets must buy the same token within
# WALLET_CORROBORATION_WINDOW_MIN minutes to count as "OGs are interested".
# Defaults to 0 (off) since OG_WALLETS starts empty — if you fill in
# OG_WALLETS above, raise this to 1 or 2 to actually require corroboration.
MIN_OG_CORROBORATION = 0
WALLET_CORROBORATION_WINDOW_MIN = 60

# ── SOCIAL / ACTIVITY SIGNAL ─────────────────────────────────────────
# "x"          — mention velocity + unique authors via X API (needs a
#                paid X_BEARER_TOKEN, see x_scanner.py)
# "dexscreener" — on-chain buy/sell activity via DexScreener, free,
#                no API key needed. Default, since it works immediately.
SIGNAL_SOURCE = os.environ.get("SIGNAL_SOURCE", "dexscreener")

# Requires your own X API credentials (paid tier — X API v2 no longer
# has a free search tier as of 2025). Only used if SIGNAL_SOURCE = "x".
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")

# Minimum mention velocity (mentions/hour) and minimum unique-author
# count before a token's social signal is considered "active" (X mode)
MIN_MENTIONS_PER_HOUR = 20
MIN_UNIQUE_AUTHORS = 8

# Thresholds for dexscreener mode — on-chain buy activity in the last hour
MIN_BUYS_PER_HOUR = 30
MIN_BUY_SELL_RATIO = 1.2       # more buys than sells = net accumulation
MIN_VOLUME_H1_USD = 5000

# ── RISK CONTROLS (non-negotiable — the bot will refuse to trade past these) ──
POSITION_SIZE_USD = 25          # fixed $ per trade — keep this small
MAX_OPEN_POSITIONS = 5
MAX_DAILY_LOSS_USD = 100        # bot halts new buys for the day once hit
STOP_LOSS_PCT = 0.20            # sell if position drops 20% from entry
TAKE_PROFIT_PCT = 0.50          # optional: sell if position gains 50%
MIN_LIQUIDITY_USD = 20000       # skip tokens with thin liquidity (rug risk)
MIN_TOKEN_AGE_MIN = 30          # skip brand-new tokens (freshly deployed = highest rug risk)

# ── PORTFOLIO / STATE ────────────────────────────────────────────────
STATE_FILE = "state/portfolio.json"
TRADE_LOG_FILE = "state/trades.csv"

# ── LOOP TIMING ──────────────────────────────────────────────────────
POLL_INTERVAL_SEC = 60
