"""
Momentum Surge Strategy.
Spec: >1.5% in 5 min on 5x volume, trailing stop 0.5%, scale-in logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal

ET = pytz.timezone("America/New_York")
SURGE_PCT = 1.5
SURGE_VOL_MULTIPLIER = 5.0
TRAILING_STOP_PCT = 0.005
INITIAL_SIZE_PCT = 0.10
MAX_SIZE_PCT = 0.20
MAX_HOLD_MINUTES = 120


class MomentumSurge(BaseStrategy):
    """Ride intraday momentum surges on huge volume."""

    name = "momentum_surge"

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        signals: List[Signal] = []
        now_et = datetime.now(ET)
        market_minutes = now_et.hour * 60 + now_et.minute

        # Active 9:45 AM to 3:30 PM
        if not (9 * 60 + 45 <= market_minutes <= 15 * 60 + 30):
            return signals

        for item in watchlist:
            symbol = item.get("symbol", "")
            rvol = item.get("rvol", 1.0)

            try:
                import pandas as pd
                df = fetcher.get_minute_bars(symbol, days=2)
                if df.empty or len(df) < 10:
                    continue

                df_et = df.copy()
                df_et.index = df_et.index.tz_convert(ET)
                today = now_et.date()
                today_df = df_et[df_et.index.date == today]
                if len(today_df) < 6:
                    continue

                current_price = float(today_df["close"].iloc[-1])
                price_5min_ago = float(today_df["close"].iloc[max(0, len(today_df) - 6)])
                pct_change_5m = (current_price - price_5min_ago) / price_5min_ago * 100

                if abs(pct_change_5m) < SURGE_PCT:
                    continue

                # Volume check: current bar vs average of last 20 bars
                recent_vol = float(today_df["volume"].iloc[-6:].mean())
                avg_vol = float(today_df["volume"].iloc[:-6].mean()) if len(today_df) > 10 else recent_vol
                vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

                if vol_ratio < SURGE_VOL_MULTIPLIER:
                    continue

                direction = "long" if pct_change_5m > 0 else "short"

                if direction == "long":
                    entry = current_price
                    stop = current_price * (1 - TRAILING_STOP_PCT)
                    # No fixed target — trailing stop manages exit
                    target = current_price * 1.02  # initial target placeholder
                else:
                    entry = current_price
                    stop = current_price * (1 + TRAILING_STOP_PCT)
                    target = current_price * 0.98

                conviction = 1
                if rvol > 5:
                    conviction += 1
                if abs(pct_change_5m) > 3.0:
                    conviction += 1

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction=direction,
                    entry_price=round(entry, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"surge={pct_change_5m:.1f}% vol_ratio={vol_ratio:.1f}x rvol={rvol:.1f}",
                ))
                logger.debug(f"MomentumSurge: {symbol} {direction} {pct_change_5m:.1f}% vol={vol_ratio:.0f}x")

            except Exception as exc:
                logger.warning(f"MomentumSurge {symbol}: {exc}")

        return signals
