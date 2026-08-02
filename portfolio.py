"""
Tracks open positions, enforces every risk cap in config.py, and logs
every trade to CSV so you can actually evaluate whether the strategy
works before ever touching live funds.

Also tracks a demo cash balance (starts at config.STARTING_BALANCE_SOL
worth of USD) so buys/sells actually draw down and replenish a
balance, like a real (paper) wallet.
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
    def __init__(self, sol_price_usd: float = None):
        os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
        self.positions: dict[str, Position] = {}
        self.realized_pnl_today = 0.0
        self.today = time.strftime("%Y-%m-%d")

        # Fallback SOL price if a live price couldn't be fetched at
        # startup - only affects the initial balance conversion, not
        # anything trade-related.
        fallback_price = sol_price_usd if sol_price_usd else 150.0
        self.starting_balance_usd = config.STARTING_BALANCE_SOL * fallback_price
        self.cash_balance_usd = self.starting_balance_usd

        self._load(fallback_price)
        self._ensure_trade_log()

    # ── persistence ──────────────────────────────────────────────
    def _load(self, fallback_price: float):
        if os.path.exists(config.STATE_FILE):
            with open(config.STATE_FILE) as f:
                data = json.load(f)
            self.positions = {
                k: Position(**v) for k, v in data.get("positions", {}).items()
            }
            self.starting_balance_usd = data.get(
                "starting_balance_usd", self.starting_balance_usd
            )
            self.cash_balance_usd = data.get(
                "cash_balance_usd", self.starting_balance_usd
            )
            if data.get("date") == self.today:
                self.realized_pnl_today = data.get("realized_pnl_today", 0.0)
        self._save()

    def _save(self):
        with open(config.STATE_FILE, "w") as f:
            json.dump(
                {
                    "positions": {k: asdict(v) for k, v in self.positions.items()},
                    "realized_pnl_today": self.realized_pnl_today,
                    "starting_balance_usd": self.starting_balance_usd,
                    "cash_balance_usd": self.cash_balance_usd,
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
    def can_open_new_position(self, size_usd: float = None) -> tuple[bool, str]:
        size_usd = size_usd if size_usd is not None else config.POSITION_SIZE_USD
        if len(self.positions) >= config.MAX_OPEN_POSITIONS:
            return False, f"max open positions reached ({config.MAX_OPEN_POSITIONS})"
        if self.realized_pnl_today <= -abs(config.MAX_DAILY_LOSS_USD):
            return False, f"daily loss limit hit (${config.MAX_DAILY_LOSS_USD}) — halted for today"
        if size_usd > self.cash_balance_usd:
            return False, f"insufficient balance (${self.cash_balance_usd:.2f} available, need ${size_usd:.2f})"
        return True, ""

    # ── actions ──────────────────────────────────────────────────
    def open_position(self, symbol: str, mint: str, price_usd: float, reason: str, size_usd: float = None):
        size_usd = size_usd if size_usd is not None else config.POSITION_SIZE_USD
        ok, why = self.can_open_new_position(size_usd)
        if not ok:
            print(f"[BLOCKED] Not opening {symbol}: {why}")
            return False, why

        if symbol in self.positions:
            return False, f"{symbol} already has an open position"
        if not price_usd or price_usd <= 0:
            return False, "no valid price available"

        tokens = size_usd / price_usd
        self.positions[symbol] = Position(
            symbol=symbol,
            mint=mint,
            entry_price_usd=price_usd,
            size_usd=size_usd,
            tokens=tokens,
            opened_at=time.time(),
        )
        self.cash_balance_usd -= size_usd
        self._save()
        self._log_trade("BUY", symbol, price_usd, size_usd, 0, reason)
        print(f"[BUY] {symbol} @ ${price_usd:.6f} — ${size_usd} ({reason})")
        return True, "opened"

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

    def close_position_manual(self, symbol: str, price_usd: float) -> tuple[bool, str]:
        """Public entry point for a user-initiated (manual) sell."""
        if symbol not in self.positions:
            return False, f"no open position for {symbol}"
        if not price_usd or price_usd <= 0:
            return False, "no valid price available"
        self._close_position(symbol, price_usd, "manual sell")
        return True, "closed"

    def _close_position(self, symbol: str, price_usd: float, reason: str):
        pos = self.positions.pop(symbol)
        current_value = pos.tokens * price_usd
        pnl = current_value - pos.size_usd
        self.realized_pnl_today += pnl
        self.cash_balance_usd += current_value
        self._save()
        self._log_trade("SELL", symbol, price_usd, current_value, pnl, reason)
        tag = "PROFIT" if pnl >= 0 else "LOSS"
        print(f"[SELL/{tag}] {symbol} @ ${price_usd:.6f} — P&L ${pnl:+.2f} ({reason})")

    def total_equity_usd(self, current_prices: dict = None) -> float:
        """Cash + current mark-to-market value of open positions."""
        current_prices = current_prices or {}
        positions_value = sum(
            p.tokens * current_prices.get(s, p.entry_price_usd)
            for s, p in self.positions.items()
        )
        return self.cash_balance_usd + positions_value

    def summary(self) -> str:
        lines = [
            f"Mode: {'PAPER' if config.PAPER_MODE else 'LIVE'}",
            f"Cash balance: ${self.cash_balance_usd:.2f} (started with ${self.starting_balance_usd:.2f})",
            f"Open positions: {len(self.positions)}/{config.MAX_OPEN_POSITIONS}",
            f"Realized P&L today: ${self.realized_pnl_today:+.2f} (limit: -${config.MAX_DAILY_LOSS_USD})",
        ]
        for s, p in self.positions.items():
            lines.append(f"  {s}: entry ${p.entry_price_usd:.6f}, size ${p.size_usd}")
        return "\n".join(lines)
