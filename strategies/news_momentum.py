"""
News & Volume Momentum Strategy.
Spec: RVOL>5, ride direction, trail 1%, exit when RVOL<2.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal

ET = pytz.timezone("America/New_York")
MIN_RVOL = 5.0
EXIT_RVOL = 2.0
TRAIL_STOP_PCT = 0.01
POSITION_SIZE_PCT = 0.15


class NewsAndVolumeMomentum(BaseStrategy):
    """
    Trade stocks with unusual volume surges — volume precedes price.
    RVOL > 5.0 is the entry signal; exit when volume dries up.
    """

    name = "news_momentum"

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        signals: List[Signal] = []
        now_et = datetime.now(ET)
        market_minutes = now_et.hour * 60 + now_et.minute

        # All day except last 5 min
        if not (9 * 60 + 30 <= market_minutes <= 15 * 60 + 55):
            return signals

        for item in watchlist:
            symbol = item.get("symbol", "")
            rvol = item.get("rvol", 1.0)

            if rvol < MIN_RVOL:
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
                if len(today_df) < 5:
                    continue

                current_price = float(today_df["close"].iloc[-1])
                open_price = float(today_df["open"].iloc[0])
                direction = "long" if current_price >= open_price else "short"

                # Price acceleration check (last 3 bars)
                recent = today_df.tail(3)
                price_momentum = float(recent["close"].iloc[-1]) - float(recent["close"].iloc[0])
                if direction == "long" and price_momentum <= 0:
                    continue
                if direction == "short" and price_momentum >= 0:
                    continue

                if direction == "long":
                    stop = current_price * (1 - TRAIL_STOP_PCT)
                    target = current_price * (1 + 0.02)
                else:
                    stop = current_price * (1 + TRAIL_STOP_PCT)
                    target = current_price * (1 - 0.02)

                conviction = 1
                if rvol > 8:
                    conviction += 1
                if rvol > 12:
                    conviction += 1

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction=direction,
                    entry_price=round(current_price, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"rvol={rvol:.1f} exit_rvol={EXIT_RVOL} trail={TRAIL_STOP_PCT*100:.1f}%",
                ))
                logger.debug(f"NewsMomentum: {symbol} {direction} rvol={rvol:.1f}")

            except Exception as exc:
                logger.warning(f"NewsMomentum {symbol}: {exc}")

        return signals
