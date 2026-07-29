"""
Main loop. Run with: python bot.py

Flow each cycle:
  1. Get candidate token symbols (YOU must supply this - see get_candidates())
  2. Fetch DexScreener pair data (liquidity, age, price, buy/sell activity)
  3. Evaluate social/activity signal (dexscreener free mode, or X paid mode)
  4. Check on-chain wallet watchlist for corroborating buys
  5. Run signal_engine.should_buy() - ALL conditions must pass
  6. If passed and risk caps allow it, open a position (paper or live)
  7. Check existing positions for stop-loss / take-profit
"""

import time
import requests

import config
from x_scanner import XScanner
import dex_scanner
from wallet_watcher import WalletWatcher
from jupiter_client import JupiterClient
from signal_engine import TokenSignal, should_buy
from portfolio import Portfolio


def get_candidates() -> list:
    """
    Returns a list of token mint addresses to evaluate this cycle.

    Pulls DexScreener's latest Solana token profiles as candidates.
    Swap in your own source (a curated watchlist, a launch-feed, etc.)
    if you prefer - there's no API that lets a bot "scan all of X for
    good memes" from nothing; you always need a starting list.
    """
    try:
        resp = requests.get(
            "https://api.dexscreener.com/token-profiles/latest/v1", timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        mints = []
        for item in data:
            if item.get("chainId") == "solana":
                mints.append(item.get("tokenAddress"))
        return mints[:20]
    except Exception as e:
        print(f"[WARN] Could not fetch candidates: {e}")
        return []


def get_pair_data(mint: str) -> dict:
    """Fetch the most-liquid DexScreener pair for a mint. Returns the
    raw pair dict (liquidity, age, price, txns, volume) or None."""
    try:
        resp = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=15
        )
        resp.raise_for_status()
        pairs = resp.json().get("pairs") or []
        if not pairs:
            return None
        return max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd", 0))
    except Exception:
        return None


def run_cycle(scanner: XScanner, watcher: WalletWatcher, jup: JupiterClient, pf: Portfolio):
    print(f"\n--- cycle @ {time.strftime('%H:%M:%S')} ---")

    # 1. update on-chain watchlist data
    watcher.poll()

    # 2. get candidates and evaluate each
    candidates = get_candidates()
    current_prices = {}

    for mint in candidates:
        pair = get_pair_data(mint)
        if not pair:
            continue

        symbol = (pair.get("baseToken") or {}).get("symbol", mint[:6])
        price_usd = float(pair.get("priceUsd", 0) or 0)
        liquidity = (pair.get("liquidity") or {}).get("usd", 0.0)
        created_at_ms = pair.get("pairCreatedAt", 0)
        age_min = (time.time() * 1000 - created_at_ms) / 60000 if created_at_ms else 0

        if price_usd:
            current_prices[symbol] = price_usd

        if symbol in pf.positions:
            continue  # already holding it, skip re-buy evaluation

        # 3. social/activity signal - source depends on config.SIGNAL_SOURCE
        if config.SIGNAL_SOURCE == "x":
            try:
                x_signal = scanner.scan_token(symbol)
                social_active = x_signal.get("is_active", False)
                social_reason = (
                    "X activity healthy" if social_active
                    else f"X mentions/hr={x_signal.get('mentions_per_hour', 0)}, "
                         f"authors={x_signal.get('unique_authors', 0)} (below threshold)"
                )
            except RuntimeError as e:
                print(f"[SKIP] X scan unavailable: {e}")
                break  # no point continuing this cycle without X access
            except Exception as e:
                print(f"[WARN] X scan failed for {symbol}: {e}")
                continue
        else:
            activity = dex_scanner.evaluate_activity(pair)
            social_active = activity["is_active"]
            social_reason = activity["reason"]

        # 4. on-chain OG wallet corroboration
        og_corroboration = watcher.corroboration_for(mint)

        signal = TokenSignal(
            symbol=symbol,
            mint=mint,
            social_active=social_active,
            social_reason=social_reason,
            og_corroboration=og_corroboration,
            liquidity_usd=liquidity,
            token_age_min=age_min,
        )

        buy, reason = should_buy(signal)
        if buy:
            pf.open_position(symbol, mint, price_usd, reason)
        else:
            print(f"[skip] {symbol}: {reason}")

    # 5. check exits on existing positions
    pf.check_exits(current_prices)

    print(pf.summary())


def main():
    print(f"Starting bot - mode: {'PAPER' if config.PAPER_MODE else 'LIVE'}")
    print(f"Signal source: {config.SIGNAL_SOURCE}")
    if not config.PAPER_MODE:
        confirm = input(
            "\n*** LIVE MODE - this will trade real funds. Type YES to continue: ***\n> "
        )
        if confirm.strip() != "YES":
            print("Aborted.")
            return

    scanner = XScanner()
    watcher = WalletWatcher()
    jup = JupiterClient()
    pf = Portfolio()

    while True:
        try:
            run_cycle(scanner, watcher, jup, pf)
        except Exception as e:
            print(f"[ERROR] cycle failed: {e}")
        time.sleep(config.POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
