# Memecoin Signal Bot (Jupiter / Solana)

Scans for tokens with active X mention velocity, corroborated by
on-chain "smart money" wallet activity, filtered by liquidity/age to
reduce rug risk. Runs in **paper mode by default** — no real funds
move until you explicitly flip a config flag.

## What this actually does

1. Pulls candidate tokens (DexScreener's latest Solana pairs by default)
2. Checks activity signal per candidate — **free by default**:
   on-chain buy/sell counts + volume from DexScreener
   (`config.SIGNAL_SOURCE = "dexscreener"`). Optionally switch to X
   mention velocity + unique authors instead
   (`SIGNAL_SOURCE = "x"`, requires a paid X API bearer token).
3. Checks whether wallets on your `OG_WALLETS` watchlist bought the
   same token recently (on-chain corroboration — harder to fake than
   either social signal)
4. Filters out thin-liquidity and brand-new tokens (highest rug risk)
5. Only buys if **all** of the above pass
6. Enforces fixed position size, max open positions, daily loss limit,
   stop-loss, and take-profit
7. Logs every trade to `state/trades.csv` so you can evaluate real
   performance before ever going live

## Setup

```bash
pip install -r requirements.txt
```

Set environment variables (none are required to get started — the
default signal source is free):

```bash
export SOLANA_RPC_URL="https://your-rpc-provider"     # recommended over public RPC
export SOLANA_PRIVATE_KEY="..."                       # ONLY needed for live mode
export SIGNAL_SOURCE="x"                               # optional — switch to X mentions
export X_BEARER_TOKEN="your_x_api_bearer_token"        # only needed if SIGNAL_SOURCE=x
```

### Two things worth doing before it's maximally useful:

1. **`config.OG_WALLETS`** — a list of Solana wallet addresses you
   actually trust as "smart money." The bot has no opinion on who
   these are; that's your judgment call. Empty list = corroboration
   check always fails = bot never buys (a safe default). Note that
   `MIN_OG_CORROBORATION` defaults to 2 — with an empty watchlist,
   nothing will ever pass. Lower it to 0 temporarily if you want to
   see the activity-signal filter working on its own first.

2. **`wallet_watcher.py`'s transfer parsing** — the current version
   fetches transaction signatures but doesn't fully parse SPL token
   transfer instructions from raw RPC responses (that's genuinely
   fiddly). For production reliability, swap in Helius' enhanced
   transactions API (https://docs.helius.dev) — a few lines to wire
   in, much more robust than parsing raw instructions by hand.

## Running

```bash
python bot.py
```

Paper mode (default) prints every decision and logs simulated trades
to `state/trades.csv` — real prices, no real money.

To go live, in `config.py` set `PAPER_MODE = False`. The bot will
still refuse to run live without explicit `YES` confirmation at
startup. Live execution (`jupiter_client.build_swap_transaction` +
signing + sending) is stubbed for you to wire up with whatever Solana
signing library you're comfortable auditing yourself — that step is
intentionally left for you to complete and review line-by-line before
it touches real funds.

## Before you go live, actually look at:

- `state/trades.csv` after a week or two of paper trading — win rate,
  average P&L per trade, whether the signal has any edge at all
- Whether `MIN_MENTIONS_PER_HOUR` / `MIN_OG_CORROBORATION` thresholds
  are producing signals frequently enough to be useful, or so rarely
  they're meaningless
- `config.POSITION_SIZE_USD` and `MAX_DAILY_LOSS_USD` — set these to
  amounts you are genuinely fine losing entirely. Memecoins can and do
  go to zero.

This is not financial advice, and nothing here changes the underlying
risk of memecoin trading — it just makes the risk visible and capped
instead of invisible and unlimited.
