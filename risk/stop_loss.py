"""
StopLossManager — per-strategy stop distances and trailing stop logic.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from loguru import logger


# Per-strategy stop distances as a fraction of entry price
STRATEGY_STOPS: Dict[str, float] = {
    "gap_fade":       0.02,   # 2% — gap extension stop
    "opening_range":  0.01,   # 1% — half the opening range (approx)
    "momentum_surge": 0.005,  # 0.5% trailing
    "vwap_bounce":    0.003,  # 0.3% through VWAP
    "overnight_swing": 0.02,  # 2% overnight
    "news_momentum":  0.01,   # 1% trailing
    "aggressor":      0.015,  # 1.5% default
    "default":        0.015,
}

# Trailing stop activates once position is up this much
TRAIL_ACTIVATION_PCT = 0.01  # 1%


class StopLossManager:
    """Manage stop prices for all open positions."""

    def get_stop_price(
        self,
        strategy_name: str,
        entry: float,
        atr: float,
        direction: str,
    ) -> float:
        """
        Calculate initial stop price for a position.
        Uses strategy-specific stop distance, with ATR as a floor.
        """
        pct = STRATEGY_STOPS.get(strategy_name, STRATEGY_STOPS["default"])
        pct_stop = entry * pct

        # ATR-based stop (min of the two = tighter stop)
        atr_stop = atr if atr > 0 else pct_stop

        stop_distance = max(pct_stop, atr_stop * 0.5)

        if direction == "long":
            return round(entry - stop_distance, 2)
        else:
            return round(entry + stop_distance, 2)

    def get_trailing_stop(
        self,
        entry: float,
        current_high: float,
        atr: float,
        direction: str,
        strategy_name: str = "default",
    ) -> float:
        """
        Calculate trailing stop once position is profitable.
        Trailing stop is a fixed % below the running high/low.
        """
        pct = STRATEGY_STOPS.get(strategy_name, STRATEGY_STOPS["default"])

        if direction == "long":
            gain_pct = (current_high - entry) / entry if entry > 0 else 0
            if gain_pct < TRAIL_ACTIVATION_PCT:
                # Not yet at trail activation — return initial stop
                return self.get_stop_price(strategy_name, entry, atr, direction)
            # Trail from the high
            trail_distance = max(current_high * pct, atr * 0.5 if atr > 0 else current_high * pct)
            return round(current_high - trail_distance, 2)
        else:
            gain_pct = (entry - current_high) / entry if entry > 0 else 0
            if gain_pct < TRAIL_ACTIVATION_PCT:
                return self.get_stop_price(strategy_name, entry, atr, direction)
            trail_distance = max(current_high * pct, atr * 0.5 if atr > 0 else current_high * pct)
            return round(current_high + trail_distance, 2)

    def check_stops(
        self,
        positions: Dict[str, dict],
        current_prices: Dict[str, float],
    ) -> List[str]:
        """
        Given open positions and current prices, return list of symbols
        whose stop has been hit.

        positions: {symbol: {"direction": ..., "stop_price": ..., ...}}
        current_prices: {symbol: current_price}
        """
        to_close: List[str] = []

        for symbol, pos in positions.items():
            price = current_prices.get(symbol)
            if price is None:
                continue

            stop = pos.get("stop_price", 0.0)
            direction = pos.get("direction", "long")

            if stop <= 0:
                continue

            if direction == "long" and price <= stop:
                logger.warning(f"STOP HIT: {symbol} long @ {price:.2f} <= stop {stop:.2f}")
                to_close.append(symbol)
            elif direction == "short" and price >= stop:
                logger.warning(f"STOP HIT: {symbol} short @ {price:.2f} >= stop {stop:.2f}")
                to_close.append(symbol)

        return to_close
