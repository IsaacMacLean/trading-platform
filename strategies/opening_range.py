"""
Opening Range Breakout (ORB) Strategy.
Spec: 15-min OR, breakout with vol confirm, stop middle of range.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal
from data.indicators import opening_range

ET = pytz.timezone("America/New_York")
OR_MINUTES = 15
VOL_CONFIRM_MULTIPLIER = 1.5
TARGET_RANGE_MULTIPLIER = 2.0
POSITION_SIZE_PCT = 0.175


class OpeningRangeBreakout(BaseStrategy):
    """Trade breakouts from the first 15-minute opening range."""

    name = "opening_range"

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        signals: List[Signal] = []
        now_et = datetime.now(ET)

        # Only fire after OR forms: 9:45–15:00
        market_minutes = now_et.hour * 60 + now_et.minute
        if not (9 * 60 + 45 <= market_minutes <= 15 * 60):
            return signals

        for item in watchlist:
            symbol = item.get("symbol", "")
            rvol = item.get("rvol", 1.0)

            # Only trade high-RVOL names
            if rvol < 2.0:
                continue

            try:
                import pandas as pd
                df = fetcher.get_minute_bars(symbol, days=2)
                if df.empty or len(df) < OR_MINUTES + 5:
                    continue

                df_et = df.copy()
                df_et.index = df_et.index.tz_convert(ET)
                today = now_et.date()
                today_df = df_et[df_et.index.date == today]
                if len(today_df) < OR_MINUTES:
                    continue

                or_high, or_low = opening_range(today_df, minutes=OR_MINUTES)
                or_range = or_high - or_low
                if or_range <= 0:
                    continue

                current_price = float(today_df["close"].iloc[-1])
                current_volume = float(today_df["volume"].iloc[-1])

                # Average volume per bar during OR
                or_df = today_df.between_time("09:30", "09:44")
                avg_or_volume = float(or_df["volume"].mean()) if not or_df.empty else 0

                vol_confirmed = avg_or_volume > 0 and current_volume >= avg_or_volume * VOL_CONFIRM_MULTIPLIER

                if current_price > or_high and vol_confirmed:
                    direction = "long"
                    entry = current_price
                    stop = or_high - or_range * 0.5  # middle of range
                    target = or_high + or_range * TARGET_RANGE_MULTIPLIER
                elif current_price < or_low and vol_confirmed:
                    direction = "short"
                    entry = current_price
                    stop = or_low + or_range * 0.5
                    target = or_low - or_range * TARGET_RANGE_MULTIPLIER
                else:
                    continue

                conviction = 1
                if rvol > 5:
                    conviction += 1
                if abs(current_price - (or_high if direction == "long" else or_low)) < or_range * 0.1:
                    conviction += 1  # tight breakout

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction=direction,
                    entry_price=round(entry, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"OR [{or_low:.2f}-{or_high:.2f}] range={or_range:.2f} rvol={rvol:.1f}",
                ))
                logger.debug(f"ORB signal: {symbol} {direction} OR=[{or_low:.2f},{or_high:.2f}]")

            except Exception as exc:
                logger.warning(f"ORB {symbol}: {exc}")

        return signals
