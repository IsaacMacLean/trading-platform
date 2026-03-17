"""
Alerts — console alerts with timestamps for key trading events.
"""
from __future__ import annotations

from datetime import datetime

import pytz
from loguru import logger

from strategies.base import Signal

ET = pytz.timezone("America/New_York")


def _ts() -> str:
    """Current ET timestamp string."""
    return datetime.now(ET).strftime("%H:%M:%S ET")


class Alerts:
    """
    Trading alert system.
    All alerts print to console via loguru with clear visual formatting.
    """

    # ------------------------------------------------------------------
    # Position events
    # ------------------------------------------------------------------

    def position_opened(
        self,
        symbol: str,
        qty: int,
        price: float,
        strategy: str,
        direction: str = "long",
    ) -> None:
        dir_str = "LONG" if direction == "long" else "SHORT"
        arrow = "▲" if direction == "long" else "▼"
        logger.info(
            f"  ┌─ POSITION OPENED ─────────────────────────────\n"
            f"  │  [{_ts()}] {arrow} {dir_str} {symbol}\n"
            f"  │  Qty: {qty} shares  @  ${price:.2f}\n"
            f"  │  Strategy: {strategy}\n"
            f"  └───────────────────────────────────────────────"
        )

    def position_closed(
        self,
        symbol: str,
        pnl: float,
        reason: str,
        pnl_pct: float = 0.0,
        hold_minutes: float = 0.0,
    ) -> None:
        emoji = "✅" if pnl >= 0 else "❌"
        sign = "+" if pnl >= 0 else ""
        logger.info(
            f"  ┌─ POSITION CLOSED ─────────────────────────────\n"
            f"  │  [{_ts()}] {emoji} {symbol}\n"
            f"  │  P&L: {sign}${pnl:.2f}  ({sign}{pnl_pct:.2f}%)  Hold: {hold_minutes:.0f}m\n"
            f"  │  Reason: {reason}\n"
            f"  └───────────────────────────────────────────────"
        )

    def stop_triggered(
        self,
        symbol: str,
        pnl: float,
        stop_price: float,
        current_price: float,
    ) -> None:
        logger.warning(
            f"  ┌─ STOP TRIGGERED ██████████████████████████████\n"
            f"  │  [{_ts()}] 🛑 {symbol}  stop=${stop_price:.2f}  price=${current_price:.2f}\n"
            f"  │  P&L: ${pnl:+,.2f}\n"
            f"  └───────────────────────────────────────────────"
        )

    # ------------------------------------------------------------------
    # Risk events
    # ------------------------------------------------------------------

    def daily_loss_approaching(self, current_pct: float, limit_pct: float) -> None:
        logger.warning(
            f"  ⚠️  DAILY LOSS APPROACHING  [{_ts()}]\n"
            f"     Current: {current_pct:.2f}%  Limit: {limit_pct:.2f}%\n"
            f"     Distance: {abs(limit_pct - current_pct):.2f}%"
        )

    def circuit_breaker_triggered(self, equity: float, pct_down: float) -> None:
        logger.critical(
            f"  ██████████████████████████████████████████████\n"
            f"  ██  CIRCUIT BREAKER TRIGGERED  [{_ts()}]  ██\n"
            f"  ██  Equity: ${equity:,.2f}  Down: {pct_down:.2f}%   ██\n"
            f"  ██  ALL POSITIONS BEING CLOSED               ██\n"
            f"  ██████████████████████████████████████████████"
        )

    def daily_halt_triggered(self, equity: float, day_pct: float) -> None:
        logger.warning(
            f"  ┌─ DAILY HALT ──────────────────────────────────\n"
            f"  │  [{_ts()}] Daily loss limit reached\n"
            f"  │  Equity: ${equity:,.2f}  Day P&L: {day_pct:.2f}%\n"
            f"  │  No new trades until tomorrow\n"
            f"  └───────────────────────────────────────────────"
        )

    def profit_lock_activated(self, equity: float, day_pct: float) -> None:
        logger.info(
            f"  ┌─ PROFIT LOCK ACTIVATED ───────────────────────\n"
            f"  │  [{_ts()}] Up {day_pct:.2f}% on the day\n"
            f"  │  Tightening all stops to breakeven\n"
            f"  └───────────────────────────────────────────────"
        )

    # ------------------------------------------------------------------
    # Signal events
    # ------------------------------------------------------------------

    def high_conviction_signal(self, signal: Signal) -> None:
        arrow = "▲" if signal.direction == "long" else "▼"
        logger.info(
            f"  ┌─ HIGH CONVICTION SIGNAL ──────────────────────\n"
            f"  │  [{_ts()}] {arrow} {signal.symbol}  [{signal.strategy}]\n"
            f"  │  Direction: {signal.direction.upper()}  Conviction: {signal.conviction}/5\n"
            f"  │  Entry: ${signal.entry_price:.2f}  Stop: ${signal.stop_price:.2f}  "
            f"Target: ${signal.target_price:.2f}\n"
            f"  │  Notes: {signal.notes[:60]}\n"
            f"  └───────────────────────────────────────────────"
        )

    def scanner_gapper(self, symbol: str, gap_pct: float, rvol: float) -> None:
        arrow = "▲" if gap_pct > 0 else "▼"
        logger.info(
            f"  🔍 GAPPER: {arrow} {symbol}  {gap_pct:+.2f}%  RVOL={rvol:.1f}x  [{_ts()}]"
        )

    def system_startup(self, equity: float, positions: int) -> None:
        logger.info(
            f"\n"
            f"  ╔══════════════════════════════════════════════╗\n"
            f"  ║     TRADING PLATFORM  —  PAPER MODE          ║\n"
            f"  ║     {_ts()}                          ║\n"
            f"  ║     Equity: ${equity:>12,.2f}                  ║\n"
            f"  ║     Open Positions: {positions:<3}                        ║\n"
            f"  ╚══════════════════════════════════════════════╝"
        )
