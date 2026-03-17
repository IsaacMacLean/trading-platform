"""
Monitor — real-time P&L tracking and stop management.
Checks all open positions every 30 seconds.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import pytz
from loguru import logger

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestBarRequest

from risk.stop_loss import StopLossManager
import config

ET = pytz.timezone("America/New_York")
CHECK_INTERVAL_SEC = 30


class Monitor:
    """
    Monitors all open positions, updates trailing stops, tracks live P&L.
    Runs in a background thread.
    Exposes state dict for the dashboard.
    """

    def __init__(self, trader=None):
        self.trading_client = TradingClient(
            config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True
        )
        self.data_client = StockHistoricalDataClient(
            config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY
        )
        self.stop_manager = StopLossManager()
        self.trader = trader  # optional Trader instance for closing positions

        self._state: Dict = {
            "positions": [],
            "account": {},
            "equity_curve": [],
            "scanner_feed": [],
            "trade_log": [],
            "risk": {},
            "status": "IDLE",
            "last_update": None,
        }
        self._state_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Track running highs/lows for trailing stops
        self._running_highs: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # State access (thread-safe)
    # ------------------------------------------------------------------

    def get_state(self) -> Dict:
        with self._state_lock:
            return dict(self._state)

    def update_state(self, **kwargs) -> None:
        with self._state_lock:
            self._state.update(kwargs)
            self._state["last_update"] = datetime.now(ET).isoformat()

    def push_scanner_result(self, items: List[dict]) -> None:
        with self._state_lock:
            self._state["scanner_feed"] = items[:50]  # keep last 50

    def push_trade(self, trade: dict) -> None:
        with self._state_lock:
            self._state["trade_log"].insert(0, trade)
            self._state["trade_log"] = self._state["trade_log"][:100]

    # ------------------------------------------------------------------
    # Core monitoring loop
    # ------------------------------------------------------------------

    def _check_once(self) -> None:
        """Single monitoring cycle."""
        try:
            # Fetch account info
            account = self.trading_client.get_account()
            equity = float(account.equity)
            cash = float(account.cash)
            buying_power = float(account.buying_power)
            last_equity = float(getattr(account, "last_equity", equity))
            day_pnl = equity - last_equity
            day_pnl_pct = day_pnl / last_equity * 100 if last_equity > 0 else 0.0

            # Fetch open positions
            alpaca_positions = self.trading_client.get_all_positions()
            symbols = [p.symbol for p in alpaca_positions]

            # Get current prices
            current_prices: Dict[str, float] = {}
            if symbols:
                try:
                    bar_req = StockLatestBarRequest(symbol_or_symbols=symbols)
                    latest = self.data_client.get_stock_latest_bar(bar_req)
                    for sym in symbols:
                        bar = latest.get(sym)
                        if bar:
                            current_prices[sym] = float(bar.close)
                except Exception as exc:
                    logger.warning(f"Monitor price fetch: {exc}")
                    for p in alpaca_positions:
                        current_prices[p.symbol] = float(p.current_price)

            # Build positions list for dashboard
            positions_list = []
            for pos in alpaca_positions:
                sym = pos.symbol
                qty = float(pos.qty)
                entry = float(pos.avg_entry_price)
                current = current_prices.get(sym, float(pos.current_price))
                unrealized = float(pos.unrealized_pl)
                unrealized_pct = float(pos.unrealized_plpc) * 100
                direction = "long" if qty > 0 else "short"

                # Update running high/low for trailing stops
                if direction == "long":
                    prev_high = self._running_highs.get(sym, entry)
                    self._running_highs[sym] = max(prev_high, current)
                else:
                    prev_high = self._running_highs.get(sym, entry)
                    self._running_highs[sym] = min(prev_high, current)

                positions_list.append({
                    "symbol": sym,
                    "direction": direction,
                    "qty": int(abs(qty)),
                    "entry_price": round(entry, 2),
                    "current_price": round(current, 2),
                    "pnl_dollars": round(unrealized, 2),
                    "pnl_pct": round(unrealized_pct, 2),
                    "stop_price": 0.0,   # managed externally
                    "target_price": 0.0,
                })

            # Check stop-loss hits using internal trader's positions if available
            if self.trader:
                trader_positions = self.trader.get_open_positions()
                to_close = self.stop_manager.check_stops(trader_positions, current_prices)
                for sym in to_close:
                    logger.warning(f"Monitor: stop hit for {sym}, closing")
                    self.trader.exit_position(sym, reason="stop")

            # Risk metrics
            day_high = max((p["pnl_pct"] for p in positions_list), default=0.0)
            total_exposure = sum(
                p["qty"] * p["current_price"] for p in positions_list
            ) / equity if equity > 0 else 0.0

            risk_info = {
                "current_drawdown_pct": round(day_pnl_pct, 2),
                "total_exposure_pct": round(total_exposure * 100, 2),
                "num_positions": len(positions_list),
                "daily_loss_limit_pct": config.DAILY_LOSS_LIMIT * 100,
                "circuit_breaker_pct": config.CIRCUIT_BREAKER_PCT * 100,
                "distance_to_daily_limit": round(
                    config.DAILY_LOSS_LIMIT * 100 - day_pnl_pct, 2
                ),
            }

            # Equity curve point
            equity_point = {
                "time": datetime.now(ET).strftime("%H:%M"),
                "equity": round(equity, 2),
            }

            # Status determination
            is_open = self.trading_client.get_clock().is_open
            status = "TRADING" if is_open and positions_list else (
                "SCANNING" if is_open else "CLOSED"
            )
            if day_pnl_pct <= config.DAILY_LOSS_LIMIT * 100:
                status = "HALTED"

            self.update_state(
                positions=positions_list,
                account={
                    "equity": round(equity, 2),
                    "cash": round(cash, 2),
                    "buying_power": round(buying_power, 2),
                    "day_pnl": round(day_pnl, 2),
                    "day_pnl_pct": round(day_pnl_pct, 2),
                    "last_equity": round(last_equity, 2),
                },
                risk=risk_info,
                status=status,
            )

            # Append equity curve point
            with self._state_lock:
                self._state["equity_curve"].append(equity_point)
                # Keep last 480 points (8 hours × 60 min × 1/min)
                self._state["equity_curve"] = self._state["equity_curve"][-480:]

        except Exception as exc:
            logger.error(f"Monitor._check_once: {exc}")

    def _run_loop(self) -> None:
        """Background monitoring loop."""
        logger.info("Monitor loop started.")
        while self._running:
            self._check_once()
            time.sleep(CHECK_INTERVAL_SEC)
        logger.info("Monitor loop stopped.")

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Monitor started.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Monitor stopped.")
