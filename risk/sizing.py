"""
PositionSizer — various position sizing approaches.
"""
from __future__ import annotations

import math
from typing import Tuple

from loguru import logger

import config


class PositionSizer:
    """Multiple position sizing strategies."""

    # ------------------------------------------------------------------
    # Fixed fractional (2% risk per trade)
    # ------------------------------------------------------------------

    def fixed_fractional(
        self,
        equity: float,
        entry: float,
        stop: float,
    ) -> int:
        """
        Size so that stop-loss distance risks exactly PER_TRADE_RISK of equity.
        Returns number of shares.
        """
        stop_distance = abs(entry - stop)
        if stop_distance <= 0 or entry <= 0:
            logger.warning("fixed_fractional: invalid entry/stop")
            return 0

        risk_dollars = equity * config.PER_TRADE_RISK
        shares = risk_dollars / stop_distance

        # Cap at max position size
        max_shares = (equity * config.MAX_POSITION_PCT) / entry
        shares = min(shares, max_shares)

        return max(1, math.floor(shares))

    # ------------------------------------------------------------------
    # Volatility-adjusted
    # ------------------------------------------------------------------

    def volatility_adjusted(
        self,
        equity: float,
        entry: float,
        atr: float,
    ) -> int:
        """
        Size inversely proportional to ATR.
        Higher ATR (more volatile) → smaller position.
        Target: ATR-based stop risks PER_TRADE_RISK.
        """
        if atr <= 0 or entry <= 0:
            return 0

        risk_dollars = equity * config.PER_TRADE_RISK
        # Stop = 1 ATR from entry
        stop_distance = atr
        shares = risk_dollars / stop_distance

        max_shares = (equity * config.MAX_POSITION_PCT) / entry
        shares = min(shares, max_shares)

        return max(1, math.floor(shares))

    # ------------------------------------------------------------------
    # Half-Kelly
    # ------------------------------------------------------------------

    def half_kelly(
        self,
        equity: float,
        entry: float,
        stop: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> int:
        """
        Half-Kelly criterion position sizing.
        f* = (p * b - q) / b  where b = avg_win/avg_loss, p = win_rate, q = 1-p
        Use half of that fraction.
        """
        if avg_loss <= 0 or entry <= 0:
            return 0

        p = max(0.0, min(1.0, win_rate))
        q = 1.0 - p
        b = avg_win / avg_loss if avg_loss > 0 else 1.0

        kelly = (p * b - q) / b if b > 0 else 0.0
        half_k = kelly * config.KELLY_FRACTION

        # Clamp between 0 and max position
        half_k = max(0.0, min(half_k, config.MAX_POSITION_PCT))

        if half_k <= 0:
            return 0

        allocation = equity * half_k
        shares = allocation / entry
        return max(1, math.floor(shares))

    # ------------------------------------------------------------------
    # Scale-in sizes
    # ------------------------------------------------------------------

    def scale_in_sizes(self, total_qty: int) -> Tuple[int, int]:
        """
        Split a total target quantity into initial and add-on tranches.
        Returns (initial_qty, addon_qty) using 60/40 split.
        Addon is only deployed if trade moves in favor.
        """
        if total_qty <= 0:
            return 0, 0

        initial = max(1, math.floor(total_qty * config.SCALE_IN_INITIAL))
        addon = max(0, total_qty - initial)
        return initial, addon
