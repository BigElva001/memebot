"""
Web dashboard for the paper-trading bot.

Two things run side by side:
  1. The automatic scanner (same as bot.py) - trades on its own
     shared "bot" account, visible to everyone, no login needed.
  2. Personal demo accounts - each friend logs in with a username +
     password (created automatically on first login) and gets their
     own persistent balance, positions, and trade history to test
     manual buying/selling with custom amounts and limits. Logging
     back in later shows exactly where they left off.

100% paper/demo mode. No private key is ever read or needed here.
"""

import os
import threading
import time

from flask import Flask, render_template, jsonify, request, session, redirect, url_for

import config
import accounts
from x_scanner import XScanner
from wallet_watcher import WalletWatcher
from jupiter_client import JupiterClient
from portfolio import Portfolio
from bot import run_cycle, get_pair_data

app = Flask(__name__)

# Sessions need a secret key to sign cookies. Set SESSION_SECRET as an
# env var on Render so logins survive a restart/redeploy; otherwise a
# random one is generated each boot and everyone gets logged out.
app.secret_key = os.environ.get("SESSION_SECRET") or os.urandom(24).hex()

# Force paper mode no matter what config.py says - this dashboard is
# for demo/testing only.
config.PAPER_MODE = True

scanner = XScanner()
watcher = WalletWatcher()
jup = JupiterClient()

try:
    _sol_price = jup._get_sol_price_usd()
except Exception:
    _sol_price = None

# Shared automatic-bot account (unauthenticated, visible to everyone).
pf = Portfolio(sol_price_usd=_sol_price)

status = {"last_run": None, "last_error": None, "cycle_count": 0}
last_known_prices = {}

# IMPORTANT: gunicorn (used in production/Render) imports this file as a
# module - it never runs the `if __name__ == "__main__":` block below.
# Background threads have to be started here, at import time, or the
# scanner and the stop-loss/take-profit watcher silently never run.
_threads_started = False


def _start_background_threads():
    global _threads_started
    if _threads_started:
        return
    _threads_started = True
    threading.Thread(target=background_loop, daemon=True).start()
    threading.Thread(target=user_positions_watch_loop, daemon=True).start()


def get_user_portfolio(username: str) -> Portfolio:
    """A fresh Portfolio backed by that user's own state file. Cheap to
    build (small JSON read) so we just construct one per request rather
    than holding N portfolios in memory."""
    safe = accounts.normalize_username(username)
    return Portfolio(
        sol_price_usd=_sol_price,
        state_file=f"state/user_{safe}_portfolio.json",
        trade_log_file=f"state/user_{safe}_trades.csv",
    )


def background_loop():
    while True:
        try:
            run_cycle(scanner, watcher, jup, pf)
            status["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
            status["last_error"] = None
        except Exception as e:
            status["last_error"] = str(e)
        status["cycle_count"] += 1
        time.sleep(config.POLL_INTERVAL_SEC)


def list_user_accounts() -> list:
    """Usernames that have a saved portfolio file, i.e. everyone who's
    ever logged in - not just currently-connected browser sessions."""
    if not os.path.isdir("state"):
        return []
    usernames = []
    for fname in os.listdir("state"):
        if fname.startswith("user_") and fname.endswith("_portfolio.json"):
            usernames.append(fname[len("user_"):-len("_portfolio.json")])
    return usernames


def user_positions_watch_loop():
    """Personal accounts don't go through bot.py's scan loop, so nothing
    else checks their stop-loss/take-profit. This loop periodically
    re-prices every open position across every user account and closes
    any that have hit their limit - this is what actually makes SL/TP
    work for manual trades."""
    while True:
        try:
            for username in list_user_accounts():
                my_pf = get_user_portfolio(username)
                if not my_pf.positions:
                    continue

                current_prices = {}
                for symbol, pos in my_pf.positions.items():
                    pair = get_pair_data(pos.mint)
                    if pair:
                        price = float(pair.get("priceUsd", 0) or 0)
                        if price:
                            current_prices[symbol] = price

                my_pf.check_exits(current_prices)
                my_pf.record_equity_point(current_prices)
        except Exception as e:
            print(f"[WARN] user_positions_watch_loop error: {e}")
        time.sleep(config.POLL_INTERVAL_SEC)


# ── auth ─────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    ok, message = accounts.register_or_login(username, password)
    if ok:
        session["username"] = accounts.normalize_username(username)
        return jsonify({"ok": True, "username": session["username"], "message": message})
    return jsonify({"ok": False, "error": message}), 400


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("username", None)
    return jsonify({"ok": True})


# ── pages ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("dashboard.html", username=session.get("username"))


# ── shared bot state (unauthenticated) ─────────────────────────────
@app.route("/api/state")
def api_state():
    import csv
    trades = []
    try:
        with open(config.TRADE_LOG_FILE) as f:
            trades = list(csv.DictReader(f))[-50:][::-1]
    except FileNotFoundError:
        pass

    return jsonify({
        "mode": "PAPER (demo funds only)",
        "status": status,
        "username": session.get("username"),
        "portfolio": {
            "cash_balance_usd": pf.cash_balance_usd,
            "starting_balance_usd": pf.starting_balance_usd,
            "starting_balance_sol": config.STARTING_BALANCE_SOL,
            "total_equity_usd": pf.total_equity_usd(last_known_prices),
            "open_positions": [
                {
                    "symbol": p.symbol,
                    "mint": p.mint,
                    "entry_price_usd": p.entry_price_usd,
                    "size_usd": p.size_usd,
                    "stop_loss_pct": p.stop_loss_pct if p.stop_loss_pct is not None else config.STOP_LOSS_PCT,
                    "take_profit_pct": p.take_profit_pct if p.take_profit_pct is not None else config.TAKE_PROFIT_PCT,
                }
                for p in pf.positions.values()
            ],
            "realized_pnl_today": pf.realized_pnl_today,
            "max_open_positions": config.MAX_OPEN_POSITIONS,
            "max_daily_loss": config.MAX_DAILY_LOSS_USD,
        },
        "recent_trades": trades,
        "config": {
            "position_size_usd": config.POSITION_SIZE_USD,
            "stop_loss_pct": config.STOP_LOSS_PCT,
            "take_profit_pct": config.TAKE_PROFIT_PCT,
            "min_liquidity_usd": config.MIN_LIQUIDITY_USD,
        },
    })


@app.route("/api/equity_history")
def api_equity_history():
    """Shared bot's total value over time."""
    return jsonify({"history": pf.equity_history})


# ── personal account state (requires login) ────────────────────────
@app.route("/api/my_state")
def api_my_state():
    username = session.get("username")
    if not username:
        return jsonify({"ok": False, "error": "not logged in"}), 401

    my_pf = get_user_portfolio(username)
    import csv
    trades = []
    try:
        with open(my_pf.trade_log_file) as f:
            trades = list(csv.DictReader(f))[-50:][::-1]
    except FileNotFoundError:
        pass

    return jsonify({
        "ok": True,
        "username": username,
        "portfolio": {
            "cash_balance_usd": my_pf.cash_balance_usd,
            "starting_balance_usd": my_pf.starting_balance_usd,
            "total_equity_usd": my_pf.total_equity_usd(last_known_prices),
            "open_positions": [
                {
                    "symbol": p.symbol,
                    "mint": p.mint,
                    "entry_price_usd": p.entry_price_usd,
                    "size_usd": p.size_usd,
                    "stop_loss_pct": p.stop_loss_pct if p.stop_loss_pct is not None else config.STOP_LOSS_PCT,
                    "take_profit_pct": p.take_profit_pct if p.take_profit_pct is not None else config.TAKE_PROFIT_PCT,
                }
                for p in my_pf.positions.values()
            ],
            "realized_pnl_today": my_pf.realized_pnl_today,
            "max_open_positions": config.MAX_OPEN_POSITIONS,
            "max_daily_loss": config.MAX_DAILY_LOSS_USD,
        },
        "recent_trades": trades,
    })


@app.route("/api/my_equity_history")
def api_my_equity_history():
    username = session.get("username")
    if not username:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    my_pf = get_user_portfolio(username)
    return jsonify({"history": my_pf.equity_history})


def _safe_pct(value, default_frac):
    """Convert a user-supplied percent (e.g. 15 for 15%) to a fraction.
    - Not provided / blank -> None (caller falls back to the global default)
    - 0 -> 0.0 (explicitly disabled - no stop-loss/take-profit at all)
    - Invalid or out of range -> None (falls back to default, safer than silently disabling)
    """
    if value in (None, "", "null"):
        return None
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return None
    if pct == 0:
        return 0.0
    if pct < 0 or pct > 95:
        return None
    return pct / 100.0


@app.route("/api/manual_buy", methods=["POST"])
def manual_buy():
    username = session.get("username")
    if not username:
        return jsonify({"ok": False, "error": "log in first to trade on your own account"}), 401

    data = request.get_json(force=True) or {}
    mint = (data.get("mint") or "").strip()
    if not mint:
        return jsonify({"ok": False, "error": "no token address provided"}), 400

    try:
        amount_usd = float(data.get("amount_usd", config.POSITION_SIZE_USD))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid amount"}), 400

    stop_loss_pct = _safe_pct(data.get("stop_loss_pct"), config.STOP_LOSS_PCT)
    take_profit_pct = _safe_pct(data.get("take_profit_pct"), config.TAKE_PROFIT_PCT)

    pair = get_pair_data(mint)
    if not pair:
        return jsonify({"ok": False, "error": "couldn't find that token on DexScreener"}), 404

    symbol = (pair.get("baseToken") or {}).get("symbol", mint[:6])
    price_usd = float(pair.get("priceUsd", 0) or 0)
    last_known_prices[symbol] = price_usd

    my_pf = get_user_portfolio(username)
    ok, reason = my_pf.open_position(
        symbol, mint, price_usd, "manual buy",
        size_usd=amount_usd,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )
    return jsonify({"ok": ok, "reason": reason, "symbol": symbol, "price_usd": price_usd})


@app.route("/api/manual_sell", methods=["POST"])
def manual_sell():
    username = session.get("username")
    if not username:
        return jsonify({"ok": False, "error": "log in first to trade on your own account"}), 401

    data = request.get_json(force=True) or {}
    symbol = (data.get("symbol") or "").strip()

    my_pf = get_user_portfolio(username)
    if not symbol or symbol not in my_pf.positions:
        return jsonify({"ok": False, "error": "no open position for that symbol"}), 404

    mint = my_pf.positions[symbol].mint
    pair = get_pair_data(mint)
    if not pair:
        return jsonify({"ok": False, "error": "couldn't fetch current price"}), 404

    price_usd = float(pair.get("priceUsd", 0) or 0)
    last_known_prices[symbol] = price_usd

    ok, reason = my_pf.close_position_manual(symbol, price_usd)
    return jsonify({"ok": ok, "reason": reason, "symbol": symbol, "price_usd": price_usd})


@app.route("/api/chart")
def api_chart():
    """Returns an embeddable DexScreener chart URL for a given mint."""
    mint = (request.args.get("mint") or "").strip()
    if not mint:
        return jsonify({"ok": False, "error": "no token address provided"}), 400

    pair = get_pair_data(mint)
    if not pair or not pair.get("url"):
        return jsonify({"ok": False, "error": "chart not available for that token"}), 404

    embed_url = pair["url"] + "?embed=1&theme=dark&trades=0&info=0"
    symbol = (pair.get("baseToken") or {}).get("symbol", mint[:6])
    return jsonify({"ok": True, "embed_url": embed_url, "symbol": symbol})


if __name__ == "__main__":
    _start_background_threads()
    app.run(host="0.0.0.0", port=5000)
else:
    # Imported by gunicorn (production) - start the background threads
    # here since __main__ never runs under gunicorn.
    _start_background_threads()
