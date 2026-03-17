"""
Gap Fade Strategy — fade large overnight gaps.
Spec: Gap >5%, enter 5 min after open, target 50% fill, stop 2% extension.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal

ET = pytz.timezone("America/New_York")
MIN_GAP_PCT = 5.0
ENTRY_DELAY_MINUTES = 5
STOP_EXTENSION_PCT = 0.02
POSITION_SIZE_PCT = 0.175  # 17.5% midpoint of 15-20%


class GapFade(BaseStrategy):
    """Fade large overnight gaps. Short gap-ups, long gap-downs."""

    name = "gap_fade"

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        signals: List[Signal] = []
        now_et = datetime.now(ET)

        # Only fire at open +5 to +30 minutes
        market_open_minutes = now_et.hour * 60 + now_et.minute
        open_start = 9 * 60 + 30 + ENTRY_DELAY_MINUTES  # 9:35
        open_end = 9 * 60 + 30 + 30  # 10:00
        if not (open_start <= market_open_minutes <= open_end):
            return signals

        for item in watchlist:
            symbol = item.get("symbol", "")
            gap_pct = item.get("gap_pct", 0.0)

            if abs(gap_pct) < MIN_GAP_PCT:
                continue

            try:
                df = fetcher.get_minute_bars(symbol, days=2)
                if df.empty or len(df) < 10:
                    continue

                import pandas as pd
                df_et = df.copy()
                df_et.index = df_et.index.tz_convert(ET)
                today = now_et.date()
                today_df = df_et[df_et.index.date == today]
                if today_df.empty:
                    continue

                current_price = float(today_df["close"].iloc[-1])
                prev_close = item.get("prev_close", current_price)
                if prev_close == 0:
                    continue

                if gap_pct > MIN_GAP_PCT:
                    # Gap UP — fade it (short or skip if restrictions)
                    direction = "short"
                    entry = current_price
                    # Target: 50% gap fill
                    gap_amount = current_price - prev_close
                    target = current_price - (gap_amount * 0.50)
                    # Stop: gap extends another 2%
                    stop = current_price * (1 + STOP_EXTENSION_PCT)
                elif gap_pct < -MIN_GAP_PCT:
                    # Gap DOWN — go long (oversold bounce)
                    direction = "long"
                    entry = current_price
                    gap_amount = prev_close - current_price
                    target = current_price + (gap_amount * 0.50)
                    stop = current_price * (1 - STOP_EXTENSION_PCT)
                else:
                    continue

                conviction = 1
                if abs(gap_pct) > 8:
                    conviction += 1

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction=direction,
                    entry_price=round(entry, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"gap={gap_pct:.1f}% prev_close={prev_close:.2f}",
                ))
                logger.debug(f"GapFade signal: {symbol} {direction} gap={gap_pct:.1f}%")

            except Exception as exc:
                logger.warning(f"GapFade {symbol}: {exc}")

        return signals
