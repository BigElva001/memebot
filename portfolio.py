"""
Tracks open positions, enforces every risk cap in config.py, and logs
every trade to CSV so you can actually evaluate whether the strategy
works before ever touching live funds.

This is the one module that should never be "trusted less" than the
signal engine — bad signals lose you the position size; bad risk
management can lose you everything.
"""

import json
import csv
import os
import time
from dataclasses import dataclass, asdict

import config


@dataclass
class Position:
    symbol: str
    mint: str
    entry_price_usd: float
    size_usd: float
    tokens: float
    opened_at: float


class Portfolio:
    def __init__(self):
        os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
        self.positions: dict[str, Position] = {}
        self.realized_pnl_today = 0.0
        self.today = time.strftime("%Y-%m-%d")
        self._load()
        self._ensure_trade_log()

    # ── persistence ──────────────────────────────────────────────
    def _load(self):
        if os.path.exists(config.STATE_FILE):
            with open(config.STATE_FILE) as f:
                data = json.load(f)
            self.positions = {
                k: Position(**v) for k, v in data.get("positions", {}).items()
            }
            if data.get("date") == self.today:
                self.realized_pnl_today = data.get("realized_pnl_today", 0.0)

    def _save(self):
        with open(config.STATE_FILE, "w") as f:
            json.dump(
                {
                    "positions": {k: asdict(v) for k, v in self.positions.items()},
                    "realized_pnl_today": self.realized_pnl_today,
                    "date": self.today,
                },
                f,
                indent=2,
            )

    def _ensure_trade_log(self):
        if not os.path.exists(config.TRADE_LOG_FILE):
            with open(config.TRADE_LOG_FILE, "w", newline="") as f:
                csv.writer(f).writerow(
                    ["timestamp", "action", "symbol", "price_usd", "size_usd", "pnl_usd", "reason", "mode"]
                )

    def _log_trade(self, action, symbol, price, size_usd, pnl_usd, reason):
        with open(config.TRADE_LOG_FILE, "a", newline="") as f:
            csv.writer(f).writerow(
                [
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    action,
                    symbol,
                    price,
                    size_usd,
                    pnl_usd,
                    reason,
                    "PAPER" if config.PAPER_MODE else "LIVE",
                ]
            )

    # ── risk gates ───────────────────────────────────────────────
    def can_open_new_position(self) -> tuple[bool, str]:
        if len(self.positions) >= config.MAX_OPEN_POSITIONS:
            return False, f"max open positions reached ({config.MAX_OPEN_POSITIONS})"
        if self.realized_pnl_today <= -abs(config.MAX_DAILY_LOSS_USD):
            return False, f"daily loss limit hit (${config.MAX_DAILY_LOSS_USD}) — halted for today"
        return True, ""

    # ── actions ──────────────────────────────────────────────────
    def open_position(self, symbol: str, mint: str, price_usd: float, reason: str):
        ok, why = self.can_open_new_position()
        if not ok:
            print(f"[BLOCKED] Not opening {symbol}: {why}")
            return False

        size_usd = config.POSITION_SIZE_USD
        tokens = size_usd / price_usd if price_usd > 0 else 0
        self.positions[symbol] = Position(
            symbol=symbol,
            mint=mint,
            entry_price_usd=price_usd,
            size_usd=size_usd,
            tokens=tokens,
            opened_at=time.time(),
        )
        self._save()
        self._log_trade("BUY", symbol, price_usd, size_usd, 0, reason)
        print(f"[BUY] {symbol} @ ${price_usd:.6f} — ${size_usd} ({reason})")
        return True

    def check_exits(self, current_prices: dict):
        """current_prices: {symbol: price_usd}. Call every loop iteration."""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            price = current_prices.get(symbol)
            if price is None:
                continue
            change_pct = (price - pos.entry_price_usd) / pos.entry_price_usd

            if change_pct <= -config.STOP_LOSS_PCT:
                self._close_position(symbol, price, "stop-loss hit")
            elif change_pct >= config.TAKE_PROFIT_PCT:
                self._close_position(symbol, price, "take-profit hit")

    def _close_position(self, symbol: str, price_usd: float, reason: str):
        pos = self.positions.pop(symbol)
        current_value = pos.tokens * price_usd
        pnl = current_value - pos.size_usd
        self.realized_pnl_today += pnl
        self._save()
        self._log_trade("SELL", symbol, price_usd, current_value, pnl, reason)
        tag = "PROFIT" if pnl >= 0 else "LOSS"
        print(f"[SELL/{tag}] {symbol} @ ${price_usd:.6f} — P&L ${pnl:+.2f} ({reason})")

    def summary(self) -> str:
        lines = [
            f"Mode: {'PAPER' if config.PAPER_MODE else 'LIVE'}",
            f"Open positions: {len(self.positions)}/{config.MAX_OPEN_POSITIONS}",
            f"Realized P&L today: ${self.realized_pnl_today:+.2f} (limit: -${config.MAX_DAILY_LOSS_USD})",
        ]
        for s, p in self.positions.items():
            lines.append(f"  {s}: entry ${p.entry_price_usd:.6f}, size ${p.size_usd}")
        return "\n".join(lines)
