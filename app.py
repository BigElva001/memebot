"""
Web dashboard for the paper-trading bot.

Runs the same scan/signal/portfolio logic as bot.py in a background
thread, and serves a live-updating web page. Also exposes manual
buy/sell endpoints so you (or friends testing it) can trade by hand
against the same demo balance, on top of whatever the automatic
scanner does.

100% paper/demo mode. No private key is ever read or needed here.
"""

import threading
import time

from flask import Flask, render_template, jsonify, request

import config
from x_scanner import XScanner
from wallet_watcher import WalletWatcher
from jupiter_client import JupiterClient
from portfolio import Portfolio
from bot import run_cycle, get_pair_data

app = Flask(__name__)

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

pf = Portfolio(sol_price_usd=_sol_price)

status = {"last_run": None, "last_error": None, "cycle_count": 0}
last_known_prices = {}


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


@app.route("/")
def index():
    return render_template("dashboard.html")


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


@app.route("/api/manual_buy", methods=["POST"])
def manual_buy():
    data = request.get_json(force=True) or {}
    mint = (data.get("mint") or "").strip()
    if not mint:
        return jsonify({"ok": False, "error": "no token address provided"}), 400

    pair = get_pair_data(mint)
    if not pair:
        return jsonify({"ok": False, "error": "couldn't find that token on DexScreener"}), 404

    symbol = (pair.get("baseToken") or {}).get("symbol", mint[:6])
    price_usd = float(pair.get("priceUsd", 0) or 0)
    last_known_prices[symbol] = price_usd

    ok, reason = pf.open_position(symbol, mint, price_usd, "manual buy")
    return jsonify({"ok": ok, "reason": reason, "symbol": symbol, "price_usd": price_usd})


@app.route("/api/manual_sell", methods=["POST"])
def manual_sell():
    data = request.get_json(force=True) or {}
    symbol = (data.get("symbol") or "").strip()
    if not symbol or symbol not in pf.positions:
        return jsonify({"ok": False, "error": "no open position for that symbol"}), 404

    mint = pf.positions[symbol].mint
    pair = get_pair_data(mint)
    if not pair:
        return jsonify({"ok": False, "error": "couldn't fetch current price"}), 404

    price_usd = float(pair.get("priceUsd", 0) or 0)
    last_known_prices[symbol] = price_usd

    ok, reason = pf.close_position_manual(symbol, price_usd)
    return jsonify({"ok": ok, "reason": reason, "symbol": symbol, "price_usd": price_usd})


if __name__ == "__main__":
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000)
