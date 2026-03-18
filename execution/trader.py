"""
Trader — wraps Alpaca API for order execution.
Tracks all trades in memory and SQLite.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pytz
from loguru import logger

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient

from strategies.base import Signal
import config

ET = pytz.timezone("America/New_York")
DB_PATH = Path(__file__).parent.parent / "trades.db"


def _init_db() -> None:
    """Create trades table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_open TEXT,
            timestamp_close TEXT,
            symbol TEXT,
            direction TEXT,
            strategy TEXT,
            shares INTEGER,
            entry_price REAL,
            exit_price REAL,
            pnl_dollars REAL,
            pnl_percent REAL,
            hold_time_minutes REAL,
            exit_reason TEXT,
            order_id TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_db()


class Trader:
    """
    Executes trades via Alpaca Paper Trading API.
    Supports market orders, limit orders, and simulated bracket orders.
    """

    def __init__(self):
        self.client = TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)
        self._open_positions: Dict[str, dict] = {}  # symbol → position info

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _submit_market_order(self, symbol: str, qty: int, side: OrderSide):
        """Submit a market order and return the order object."""
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order_data=req)

    def _place_broker_stop(
        self, symbol: str, qty: int, direction: str, stop_price: float
    ) -> Optional[str]:
        """
        Place a GTC stop-loss order directly on Alpaca.
        Survives bot crashes — the broker will execute it regardless of bot state.
        """
        try:
            side = OrderSide.SELL if direction == "long" else OrderSide.BUY
            req = StopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                stop_price=round(stop_price, 2),
                time_in_force=TimeInForce.GTC,
            )
            order = self.client.submit_order(order_data=req)
            logger.info(f"Broker stop placed: {symbol} {side.value} x{qty} @ ${stop_price:.2f}")
            return str(order.id)
        except Exception as exc:
            logger.warning(f"_place_broker_stop {symbol}: {exc} — using software stop only")
            return None

    def _submit_limit_order(self, symbol: str, qty: int, side: OrderSide, limit_price: float):
        """Submit a limit order."""
        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            limit_price=round(limit_price, 2),
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order_data=req)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enter_long(self, signal: Signal) -> Optional[str]:
        """
        Enter a long position. Uses market order for momentum strategies,
        limit order for mean-reversion strategies.
        Returns order_id or None on failure.
        """
        symbol = signal.symbol
        qty = signal.qty if signal.qty > 0 else 1

        try:
            if signal.strategy in config.LIMIT_ORDER_STRATEGIES:
                order = self._submit_limit_order(
                    symbol, qty, OrderSide.BUY, signal.entry_price
                )
            else:
                order = self._submit_market_order(symbol, qty, OrderSide.BUY)

            order_id = str(order.id)
            self._open_positions[symbol] = {
                "direction": "long",
                "qty": qty,
                "entry_price": signal.entry_price,
                "stop_price": signal.stop_price,
                "target_price": signal.target_price,
                "strategy": signal.strategy,
                "entry_time": datetime.now(ET).isoformat(),
                "order_id": order_id,
            }
            logger.info(f"ENTER LONG {symbol} x{qty} @ ~{signal.entry_price:.2f} [{signal.strategy}]")
            # Place hard stop on Alpaca — survives bot restarts
            if signal.stop_price > 0:
                self._place_broker_stop(symbol, qty, "long", signal.stop_price)
            return order_id

        except Exception as exc:
            logger.error(f"enter_long {symbol}: {exc}")
            return None

    def enter_short(self, signal: Signal) -> Optional[str]:
        """
        Enter a short position. Paper trading only.
        Returns order_id or None on failure.
        """
        symbol = signal.symbol
        qty = signal.qty if signal.qty > 0 else 1

        try:
            if signal.strategy in config.LIMIT_ORDER_STRATEGIES:
                order = self._submit_limit_order(
                    symbol, qty, OrderSide.SELL, signal.entry_price
                )
            else:
                order = self._submit_market_order(symbol, qty, OrderSide.SELL)

            order_id = str(order.id)
            self._open_positions[symbol] = {
                "direction": "short",
                "qty": qty,
                "entry_price": signal.entry_price,
                "stop_price": signal.stop_price,
                "target_price": signal.target_price,
                "strategy": signal.strategy,
                "entry_time": datetime.now(ET).isoformat(),
                "order_id": order_id,
            }
            logger.info(f"ENTER SHORT {symbol} x{qty} @ ~{signal.entry_price:.2f} [{signal.strategy}]")
            # Place hard stop on Alpaca — survives bot restarts
            if signal.stop_price > 0:
                self._place_broker_stop(symbol, qty, "short", signal.stop_price)
            return order_id

        except Exception as exc:
            logger.error(f"enter_short {symbol}: {exc}")
            return None

    def exit_position(self, symbol: str, reason: str = "manual") -> bool:
        """
        Close an open position with a market order.
        Returns True on success.
        """
        try:
            self.client.close_position(symbol)
            pos = self._open_positions.pop(symbol, {})
            logger.info(f"EXIT {symbol} reason={reason}")
            self._log_trade(symbol, pos, reason=reason)
            return True
        except Exception as exc:
            logger.error(f"exit_position {symbol}: {exc}")
            return False

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        stop: float,
        target: float,
    ) -> Optional[str]:
        """
        Simulate a bracket order: enter + schedule stop and target monitoring.
        Alpaca paper supports bracket orders via client_order_id tracking.
        We use a market entry and then rely on the monitor to handle OCO.
        """
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        try:
            order = self._submit_market_order(symbol, qty, order_side)
            order_id = str(order.id)
            direction = "long" if side.lower() == "buy" else "short"
            self._open_positions[symbol] = {
                "direction": direction,
                "qty": qty,
                "entry_price": 0.0,  # will update on fill
                "stop_price": stop,
                "target_price": target,
                "strategy": "bracket",
                "entry_time": datetime.now(ET).isoformat(),
                "order_id": order_id,
            }
            logger.info(f"BRACKET {symbol} {side} x{qty} stop={stop:.2f} target={target:.2f}")
            return order_id
        except Exception as exc:
            logger.error(f"place_bracket_order {symbol}: {exc}")
            return None

    def get_open_positions(self) -> Dict[str, dict]:
        """Return internal open positions dict."""
        return dict(self._open_positions)

    def sync_positions_from_broker(self) -> None:
        """Sync internal state with actual Alpaca positions."""
        try:
            alpaca_positions = self.client.get_all_positions()
            self._open_positions = {}
            for pos in alpaca_positions:
                sym = pos.symbol
                direction = "long" if float(pos.qty) > 0 else "short"
                self._open_positions[sym] = {
                    "direction": direction,
                    "qty": abs(int(float(pos.qty))),
                    "entry_price": float(pos.avg_entry_price),
                    "stop_price": 0.0,
                    "target_price": 0.0,
                    "strategy": "unknown",
                    "entry_time": datetime.now(ET).isoformat(),
                }
        except Exception as exc:
            logger.error(f"sync_positions_from_broker: {exc}")

    def close_all_positions(self) -> None:
        """Emergency: close all open positions."""
        logger.warning("CLOSING ALL POSITIONS")
        try:
            self.client.close_all_positions(cancel_orders=True)
            self._open_positions.clear()
            logger.info("All positions closed.")
        except Exception as exc:
            logger.error(f"close_all_positions: {exc}")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _log_trade(self, symbol: str, pos: dict, reason: str = "") -> None:
        """Log a completed trade to SQLite."""
        try:
            now_str = datetime.now(ET).isoformat()
            entry_price = pos.get("entry_price", 0.0)
            exit_price = 0.0  # filled by monitor
            qty = pos.get("qty", 0)
            pnl = 0.0
            pnl_pct = 0.0
            direction = pos.get("direction", "long")
            entry_time = pos.get("entry_time", now_str)
            hold_minutes = 0.0

            try:
                dt_entry = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                dt_exit = datetime.now(ET)
                hold_minutes = (dt_exit - dt_entry).total_seconds() / 60
            except Exception:
                pass

            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                """INSERT INTO trades
                   (timestamp_open, timestamp_close, symbol, direction, strategy,
                    shares, entry_price, exit_price, pnl_dollars, pnl_percent,
                    hold_time_minutes, exit_reason, order_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry_time, now_str, symbol, direction, pos.get("strategy", ""),
                    qty, entry_price, exit_price, pnl, pnl_pct,
                    hold_minutes, reason, pos.get("order_id", ""),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"_log_trade {symbol}: {exc}")
