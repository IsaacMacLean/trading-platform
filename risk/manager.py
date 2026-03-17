"""
RiskManager — enforces all platform risk limits.
"""
from __future__ import annotations

import math
from typing import Dict, List

from loguru import logger

import config

# Legacy functions kept for backward compat
from config import RISK_PER_TRADE, ATR_MULTIPLIER, MAX_POSITION_PCT


def position_size(equity: float, entry: float, atr: float) -> int:
    """Legacy function: size by ATR risk."""
    stop_distance = ATR_MULTIPLIER * atr
    if stop_distance <= 0 or entry <= 0:
        return 0
    risk_dollars = equity * RISK_PER_TRADE
    shares_by_risk = risk_dollars / stop_distance
    max_shares = (equity * MAX_POSITION_PCT) / entry
    shares = min(shares_by_risk, max_shares)
    return max(1, math.floor(shares))


def stop_price(entry: float, atr: float) -> float:
    """Legacy function: ATR-based stop."""
    return round(entry - ATR_MULTIPLIER * atr, 2)


class RiskManager:
    """
    Central risk enforcement.
    All checks return True when the risk condition is triggered (halt / go flat).
    """

    def __init__(self, starting_equity: float = 100_000.0):
        self.starting_equity = starting_equity
        self._halted_today = False
        self._circuit_broken = False

    # ------------------------------------------------------------------
    # Daily loss limit
    # ------------------------------------------------------------------

    def check_daily_loss_limit(self, account) -> bool:
        """
        Returns True if daily loss limit is breached → halt new trades.
        Limit: -5% from starting equity for the day.
        """
        try:
            equity = float(account.equity)
            last_equity = float(getattr(account, "last_equity", self.starting_equity))
            daily_return = (equity - last_equity) / last_equity if last_equity > 0 else 0.0

            if daily_return <= config.DAILY_LOSS_LIMIT:
                if not self._halted_today:
                    logger.warning(
                        f"DAILY LOSS LIMIT HIT: {daily_return*100:.2f}% "
                        f"(limit={config.DAILY_LOSS_LIMIT*100:.1f}%)"
                    )
                    self._halted_today = True
                return True
        except Exception as exc:
            logger.error(f"check_daily_loss_limit: {exc}")
        return False

    def reset_daily_halt(self) -> None:
        """Call at start of each new trading day."""
        self._halted_today = False

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    def check_circuit_breaker(self, account, starting_equity: float | None = None) -> bool:
        """
        Returns True if portfolio is down >15% from starting capital → go flat.
        """
        base = starting_equity or self.starting_equity
        try:
            equity = float(account.equity)
            total_return = (equity - base) / base if base > 0 else 0.0

            if total_return <= config.CIRCUIT_BREAKER_PCT:
                if not self._circuit_broken:
                    logger.critical(
                        f"CIRCUIT BREAKER TRIGGERED: {total_return*100:.2f}% from start "
                        f"(limit={config.CIRCUIT_BREAKER_PCT*100:.1f}%)"
                    )
                    self._circuit_broken = True
                return True
        except Exception as exc:
            logger.error(f"check_circuit_breaker: {exc}")
        return False

    # ------------------------------------------------------------------
    # Profit lock
    # ------------------------------------------------------------------

    def check_profit_lock(self, account) -> bool:
        """
        Returns True if up >3% on the day → tighten all stops to breakeven.
        """
        try:
            equity = float(account.equity)
            last_equity = float(getattr(account, "last_equity", self.starting_equity))
            daily_return = (equity - last_equity) / last_equity if last_equity > 0 else 0.0

            if daily_return >= config.PROFIT_LOCK_THRESHOLD:
                logger.info(
                    f"PROFIT LOCK: up {daily_return*100:.2f}% — tightening stops to breakeven"
                )
                return True
        except Exception as exc:
            logger.error(f"check_profit_lock: {exc}")
        return False

    # ------------------------------------------------------------------
    # Position limits
    # ------------------------------------------------------------------

    def can_open_position(self, account, positions: Dict) -> bool:
        """
        Returns True if a new position can be opened.
        Checks:
          - MAX_SIMULTANEOUS_POSITIONS
          - MAX_TOTAL_EXPOSURE
          - Not halted / circuit broken
        """
        if self._halted_today or self._circuit_broken:
            logger.warning("Cannot open position: system halted")
            return False

        if len(positions) >= config.MAX_SIMULTANEOUS_POSITIONS:
            logger.debug(f"Max positions reached: {len(positions)}/{config.MAX_SIMULTANEOUS_POSITIONS}")
            return False

        try:
            equity = float(account.equity)
            portfolio_value = float(getattr(account, "portfolio_value", equity))
            long_market_value = float(getattr(account, "long_market_value", 0.0))
            short_market_value = abs(float(getattr(account, "short_market_value", 0.0)))
            total_exposure = (long_market_value + short_market_value) / equity if equity > 0 else 0.0

            if total_exposure >= config.MAX_TOTAL_EXPOSURE:
                logger.debug(f"Max exposure reached: {total_exposure*100:.1f}%")
                return False
        except Exception as exc:
            logger.error(f"can_open_position exposure check: {exc}")

        return True

    def max_position_value(self, equity: float) -> float:
        """Return max dollar value for a single position."""
        return equity * config.MAX_POSITION_PCT
