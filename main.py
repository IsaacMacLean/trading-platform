"""
main.py — Entry point for the Aggressive Short-Term Trading Platform.

Wires together all components:
  - AlpacaFetcher (data)
  - Scanner (universe filtering)
  - Aggressor (meta-strategy)
  - RiskManager + PositionSizer
  - Trader (execution)
  - Scheduler (APScheduler jobs)
  - Monitor (position tracking)
  - TradeLogger + Alerts (reporting)

Run with:  python main.py
"""
from __future__ import annotations

import signal
import sys
import time
from datetime import datetime
from typing import List

import pytz
from loguru import logger

import config
from data.fetcher import AlpacaFetcher
from data.scanner import Scanner
from data.universe import get_tradeable_universe, BASE_UNIVERSE
from data import indicators

from strategies.aggressor import Aggressor
from strategies.base import Signal

from risk.manager import RiskManager
from risk.sizing import PositionSizer

from execution.trader import Trader
from execution.scheduler import Scheduler
from execution.monitor import Monitor

from reporting.trade_log import TradeLogger
from reporting.alerts import Alerts
from reporting.performance import generate_eod_report

ET = pytz.timezone("America/New_York")

# Daily trade counter — resets each morning, hard-caps overtrading
_trades_today: int = 0

# ---- Configure loguru ----
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level="INFO",
    colorize=True,
)
logger.add(
    "logs/trading_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
    encoding="utf-8",
)


# ===========================================================================
# Global component instances
# ===========================================================================

fetcher = AlpacaFetcher()
scanner = Scanner(fetcher=fetcher)
aggressor = Aggressor()
risk_manager = RiskManager()
sizer = PositionSizer()
trader = Trader()
monitor = Monitor(trader=trader)
scheduler = Scheduler()
trade_logger = TradeLogger()
alerts = Alerts()


def get_universe() -> List[str]:
    """Return today's tradeable universe."""
    return BASE_UNIVERSE[:100]  # use first 100 for speed


# ===========================================================================
# Scheduled job callbacks
# ===========================================================================

def job_premarket_scan() -> None:
    """7:00 AM — fetch pre-market data, identify gappers."""
    global _trades_today
    _trades_today = 0  # reset daily trade counter each morning
    logger.info("=== PRE-MARKET SCAN ===")
    universe = get_universe()
    try:
        gappers = scanner.scan_premarket(universe)
        aggressor.set_top_gappers(gappers)
        monitor.push_scanner_result(gappers)
        for g in gappers[:5]:
            alerts.scanner_gapper(g["symbol"], g.get("gap_pct", 0), g.get("rvol", 0))
    except Exception as exc:
        logger.error(f"job_premarket_scan: {exc}")


def job_final_scan() -> None:
    """9:25 AM — final pre-market scan, prepare orders."""
    logger.info("=== FINAL PRE-MARKET SCAN ===")
    universe = get_universe()
    try:
        watchlist = scanner.scan_premarket(universe)
        monitor.push_scanner_result(watchlist)
        logger.info(f"Final scan: {len(watchlist)} candidates ready")
    except Exception as exc:
        logger.error(f"job_final_scan: {exc}")


def job_opening_range_calc() -> None:
    """9:35 AM — calculate opening range levels."""
    logger.info("=== OPENING RANGE CALC ===")
    # ORB strategy will pick these up from market data at signal time


def job_first_trades() -> None:
    """9:45 AM — fire ORB and gap fade signals."""
    logger.info("=== FIRST TRADES (ORB + GAP FADE) ===")
    _run_aggressor_cycle()


def job_intraday_scan() -> None:
    """Every 1 minute — momentum surge, VWAP bounce, unusual volume."""
    now_et = datetime.now(ET)
    market_min = now_et.hour * 60 + now_et.minute
    # Only active 9:45 AM – 3:30 PM
    if not (9 * 60 + 45 <= market_min <= 15 * 60 + 30):
        return

    universe = get_universe()
    try:
        movers = scanner.scan_intraday(universe)
        if movers:
            monitor.push_scanner_result(movers)
        # Run aggressor every 5 minutes
        if now_et.minute % 5 == 0:
            _run_aggressor_cycle()
    except Exception as exc:
        logger.error(f"job_intraday_scan: {exc}")


def job_close_overnight() -> None:
    """9:45 AM — close overnight swing positions (spec: open +15 min exit)."""
    logger.info("=== CLOSING OVERNIGHT POSITIONS ===")
    try:
        open_positions = trader.get_open_positions()
        for symbol, pos in list(open_positions.items()):
            if pos.get("strategy") == "overnight_swing":
                logger.info(f"Closing overnight position: {symbol}")
                trader.exit_position(symbol, reason="overnight_exit")
    except Exception as exc:
        logger.error(f"job_close_overnight: {exc}")


def job_overnight_scan() -> None:
    """3:30 PM — overnight swing scanner."""
    logger.info("=== OVERNIGHT SWING SCAN ===")
    universe = get_universe()
    try:
        watchlist = scanner.get_todays_watchlist(universe)
        monitor.push_scanner_result(watchlist)
    except Exception as exc:
        logger.error(f"job_overnight_scan: {exc}")


def job_overnight_entries() -> None:
    """3:45 PM — enter overnight positions if signals present."""
    logger.info("=== OVERNIGHT ENTRIES ===")
    _run_aggressor_cycle(overnight_only=True)


def job_close_intraday() -> None:
    """3:55 PM — close all intraday-only positions."""
    logger.info("=== CLOSING INTRADAY POSITIONS ===")
    try:
        open_positions = trader.get_open_positions()
        for symbol, pos in list(open_positions.items()):
            strategy = pos.get("strategy", "")
            if strategy != "overnight_swing":
                logger.info(f"Closing intraday position: {symbol}")
                trader.exit_position(symbol, reason="eod_intraday")
    except Exception as exc:
        logger.error(f"job_close_intraday: {exc}")


def job_eod_report() -> None:
    """4:00 PM — generate daily report."""
    logger.info("=== EOD REPORT ===")
    try:
        account = trader.client.get_account()
        trades = trade_logger.get_today_trades()
        generate_eod_report(trades, account)
    except Exception as exc:
        logger.error(f"job_eod_report: {exc}")


# ===========================================================================
# Core trading cycle
# ===========================================================================

def _run_aggressor_cycle(overnight_only: bool = False) -> None:  # noqa: C901
    """
    Run the full Aggressor cycle:
    1. Get watchlist
    2. Generate signals via Aggressor
    3. Apply risk checks
    4. Size positions
    5. Execute
    """
    global _trades_today
    try:
        # Hard cap on daily trades — prevents overtrading on noisy days
        if _trades_today >= config.MAX_DAILY_TRADES:
            logger.info(f"Daily trade limit reached ({_trades_today}/{config.MAX_DAILY_TRADES})")
            return

        # Check risk before doing anything
        account = trader.client.get_account()
        equity = float(account.equity)

        if risk_manager.check_circuit_breaker(account):
            logger.warning("Circuit breaker active — closing positions and cancelling all orders")
            try:
                trader.client.cancel_orders()  # cancel pending orders first
            except Exception as exc:
                logger.warning(f"cancel_orders: {exc}")
            trader.close_all_positions()
            return

        if risk_manager.check_daily_loss_limit(account):
            logger.warning("Daily loss limit — halted")
            return

        # Profit lock: tighten stops but continue
        if risk_manager.check_profit_lock(account):
            alerts.profit_lock_activated(equity, float(account.equity) / float(account.last_equity) * 100 - 100)

        positions = trader.get_open_positions()
        if not risk_manager.can_open_position(account, positions):
            logger.debug("Cannot open new positions (max reached or halted)")
            return

        # Enforce overnight position limit
        if overnight_only:
            overnight_count = sum(
                1 for p in positions.values() if p.get("strategy") == "overnight_swing"
            )
            if overnight_count >= config.OVERNIGHT_MAX_POSITIONS:
                logger.info(
                    f"Overnight limit reached ({overnight_count}/{config.OVERNIGHT_MAX_POSITIONS})"
                )
                return

        # Get watchlist
        universe = get_universe()
        watchlist = scanner.get_todays_watchlist(universe)

        if not watchlist:
            logger.debug("No watchlist candidates")
            return

        # Generate aggressor signals
        raw_signals: List[Signal] = aggressor.generate_signals(watchlist, fetcher, indicators)

        if not raw_signals:
            return

        # Size positions from REMAINING undeployed capital, not total equity.
        # If 3 positions are already open at 20% each, only 40% of capital is free.
        deployed = sum(
            p.get("qty", 0) * p.get("entry_price", 0) for p in positions.values()
        )
        available_equity = max(equity * 0.10, equity - deployed)  # keep at least 10% floor
        sized_signals = aggressor.apply_position_sizing(raw_signals, available_equity)

        # Execute top signals
        for sig in sized_signals:
            if sig.symbol in positions:
                logger.debug(f"Already in {sig.symbol}, skipping")
                continue

            if not risk_manager.can_open_position(account, trader.get_open_positions()):
                break

            # Skip if overnight_only mode but not overnight strategy
            if overnight_only and sig.strategy != "overnight_swing":
                continue

            # Alert
            if sig.conviction >= 3:
                alerts.high_conviction_signal(sig)

            # Execute
            order_id = None
            if sig.direction == "long":
                order_id = trader.enter_long(sig)
            else:
                order_id = trader.enter_short(sig)

            if order_id:
                _trades_today += 1
                alerts.position_opened(sig.symbol, sig.qty, sig.entry_price, sig.strategy, sig.direction)
                trade_logger.log_trade({
                    "symbol": sig.symbol,
                    "direction": sig.direction,
                    "strategy": sig.strategy,
                    "shares": sig.qty,
                    "entry_price": sig.entry_price,
                    "order_id": order_id,
                })

    except Exception as exc:
        logger.error(f"_run_aggressor_cycle: {exc}")


# ===========================================================================
# Startup banner
# ===========================================================================

def print_banner() -> None:
    try:
        account = trader.client.get_account()
        equity = float(account.equity)
        buying_power = float(account.buying_power)
        n_positions = len(trader.client.get_all_positions())
        alerts.system_startup(equity, n_positions)
        logger.info(f"  Account Status : {account.status}")
        logger.info(f"  Equity         : ${equity:,.2f}")
        logger.info(f"  Buying Power   : ${buying_power:,.2f}")
        logger.info(f"  Open Positions : {n_positions}")
        logger.info(f"  Universe Size  : {len(BASE_UNIVERSE)} symbols")
        logger.info(f"  Strategies     : Gap Fade, ORB, Momentum, VWAP, Overnight, News")
        logger.info(f"  Dashboard      : http://localhost:{config.DASHBOARD_PORT}")
    except Exception as exc:
        logger.warning(f"print_banner: {exc}")


# ===========================================================================
# Graceful shutdown
# ===========================================================================

_shutdown = False


def _handle_signal(signum, frame) -> None:
    global _shutdown
    logger.warning(f"Shutdown signal received ({signum})")
    _shutdown = True


def shutdown() -> None:
    logger.info("Shutting down...")
    monitor.stop()
    scheduler.stop()
    logger.info("Goodbye.")


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    # Register signal handlers
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Startup
    print_banner()

    # Sync positions from broker
    trader.sync_positions_from_broker()

    # Register scheduler callbacks
    scheduler.register("premarket_scan",    job_premarket_scan)
    scheduler.register("final_scan",        job_final_scan)
    scheduler.register("opening_range_calc", job_opening_range_calc)
    scheduler.register("close_overnight",   job_close_overnight)
    scheduler.register("first_trades",      job_first_trades)
    scheduler.register("intraday_scan",     job_intraday_scan)
    scheduler.register("overnight_scan",    job_overnight_scan)
    scheduler.register("overnight_entries", job_overnight_entries)
    scheduler.register("close_intraday",    job_close_intraday)
    scheduler.register("eod_report",        job_eod_report)

    # Start components
    monitor.start()
    scheduler.start()

    logger.info("Trading platform running. Press Ctrl+C to stop.")
    logger.info(f"Jobs scheduled:")
    scheduler.list_jobs()

    # Main loop — keep alive, let APScheduler and monitor thread do the work
    try:
        while not _shutdown:
            time.sleep(1)
    finally:
        shutdown()


if __name__ == "__main__":
    main()
