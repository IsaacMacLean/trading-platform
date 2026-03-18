"""
Gap Fade Strategy — fade large overnight gaps WITH reversal confirmation.
Only fires when the opening candle shows price reversing back toward prior close.
Spec: Gap 5-12%, reversal candle confirmed, 2.5% stop, 50% fill target.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal
import config

ET = pytz.timezone("America/New_York")
MIN_GAP_PCT = 5.0
MAX_GAP_PCT = config.GAP_FADE_MAX_GAP   # 12% — above this likely hard news, don't fade
ENTRY_DELAY_MINUTES = 5
STOP_EXTENSION_PCT = config.GAP_FADE_STOP_PCT  # 2.5% (was 2%)


class GapFade(BaseStrategy):
    """
    Fade large overnight gaps — but ONLY when the first few candles confirm reversal.
    Gap-up fade: opening candle must be bearish (close < open at open bar).
    Gap-down fade: opening candle must be bullish (close > open at open bar).
    """

    name = "gap_fade"

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        signals: List[Signal] = []
        now_et = datetime.now(ET)

        # Fire at open +5 to +25 minutes (9:35–9:55)
        market_open_minutes = now_et.hour * 60 + now_et.minute
        open_start = 9 * 60 + 30 + ENTRY_DELAY_MINUTES  # 9:35
        open_end = 9 * 60 + 55                            # 9:55
        if not (open_start <= market_open_minutes <= open_end):
            return signals

        for item in watchlist:
            symbol = item.get("symbol", "")
            gap_pct = item.get("gap_pct", 0.0)

            # Only fade gaps within a meaningful but not news-driven range
            if abs(gap_pct) < MIN_GAP_PCT or abs(gap_pct) > MAX_GAP_PCT:
                continue

            try:
                import pandas as pd
                df = fetcher.get_minute_bars(symbol, days=2)
                if df.empty or len(df) < 10:
                    continue

                df_et = df.copy()
                df_et.index = df_et.index.tz_convert(ET)
                today = now_et.date()
                today_df = df_et[df_et.index.date == today]
                if len(today_df) < 3:
                    continue

                current_price = float(today_df["close"].iloc[-1])
                prev_close = item.get("prev_close", current_price)
                if prev_close == 0:
                    continue

                # Opening bar (first bar of day)
                open_bar = today_df.iloc[0]
                open_bar_open = float(open_bar["open"])
                open_bar_close = float(open_bar["close"])
                open_bar_high = float(open_bar["high"])

                if gap_pct > MIN_GAP_PCT:
                    # Gap UP fade → want to short
                    # Reversal confirmation: opening candle is bearish AND
                    # current price is below the open-bar's high (not still running up)
                    bearish_candle = open_bar_close < open_bar_open
                    price_stalling = current_price < open_bar_high

                    if not (bearish_candle and price_stalling):
                        continue  # skip if price is still running up

                    direction = "short"
                    entry = current_price
                    gap_amount = current_price - prev_close
                    target = current_price - (gap_amount * 0.50)
                    stop = current_price * (1 + STOP_EXTENSION_PCT)

                elif gap_pct < -MIN_GAP_PCT:
                    # Gap DOWN fade → want to long
                    # Reversal confirmation: opening candle is bullish (buyers stepping in)
                    bullish_candle = open_bar_close > open_bar_open
                    if not bullish_candle:
                        continue  # skip if selling pressure continues

                    direction = "long"
                    entry = current_price
                    gap_amount = prev_close - current_price
                    target = current_price + (gap_amount * 0.50)
                    stop = current_price * (1 - STOP_EXTENSION_PCT)
                else:
                    continue

                conviction = 1
                if abs(gap_pct) > 7:
                    conviction += 1  # larger gaps have more fill potential

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction=direction,
                    entry_price=round(entry, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"gap={gap_pct:.1f}% prev_close={prev_close:.2f} reversal_confirmed=True",
                ))
                logger.debug(f"GapFade signal: {symbol} {direction} gap={gap_pct:.1f}%")

            except Exception as exc:
                logger.warning(f"GapFade {symbol}: {exc}")

        return signals
