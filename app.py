"""
Web dashboard for the paper-trading bot.

Runs the same scan/signal/portfolio logic as bot.py, but in a
background thread, and serves a live-updating web page so you (and
friends testing it) can watch it work from a browser — no coding
needed on their end, just open the link.

100% paper/demo mode. No private key is ever read or needed for this
version.
"""

import threading
import time
import json

from flask import Flask, render_template, jsonify

import config
from x_scanner import XScanner
from wallet_watcher import WalletWatcher
from jupiter_client import JupiterClient
from portfolio import Portfolio
from bot import run_cycle

app = Flask(__name__)

# Force paper mode no matter what config.py says — this dashboard is
# for demo/testing only.
config.PAPER_MODE = True

scanner = XScanner()
watcher = WalletWatcher()
jup = JupiterClient()
pf = Portfolio()

status = {"last_run": None, "last_error": None, "cycle_count": 0}


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
            "open_positions": [
                {
                    "symbol": p.symbol,
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


if __name__ == "__main__":
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000)
