"""
Overnight Swing Strategy.
Spec: At 3:30 PM, stocks up >3% with RVOL>2, above VWAP and all MAs.
Buy at 3:45 PM, sell next day open +15 min, stop -2%.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal
from data.indicators import add_vwap, add_ema

ET = pytz.timezone("America/New_York")
MIN_UP_PCT = 3.0
MIN_RVOL = 2.0
STOP_PCT = 0.02
POSITION_SIZE_PCT = 0.225  # 22.5% midpoint of 20-25%


class OvernightSwing(BaseStrategy):
    """Hold momentum stocks overnight for gap-up continuation."""

    name = "overnight_swing"

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        signals: List[Signal] = []
        now_et = datetime.now(ET)
        market_minutes = now_et.hour * 60 + now_et.minute

        # Fire between 3:30 PM and 3:50 PM
        if not (15 * 60 + 30 <= market_minutes <= 15 * 60 + 50):
            return signals

        for item in watchlist:
            symbol = item.get("symbol", "")
            rvol = item.get("rvol", 1.0)

            if rvol < MIN_RVOL:
                continue

            try:
                import pandas as pd
                df = fetcher.get_minute_bars(symbol, days=2)
                if df.empty or len(df) < 30:
                    continue

                df_et = df.copy()
                df_et.index = df_et.index.tz_convert(ET)
                today = now_et.date()
                today_df = df_et[df_et.index.date == today]
                if len(today_df) < 20:
                    continue

                today_df = add_vwap(today_df)
                today_df = add_ema(today_df, fast=9, slow=21)

                current_price = float(today_df["close"].iloc[-1])
                open_price = float(today_df["open"].iloc[0])

                pct_change = (current_price - open_price) / open_price * 100
                if pct_change < MIN_UP_PCT:
                    continue

                vwap = today_df["vwap"].iloc[-1] if "vwap" in today_df.columns else current_price
                ema_9 = today_df["ema_9"].iloc[-1] if "ema_9" in today_df.columns else current_price
                ema_21 = today_df["ema_21"].iloc[-1] if "ema_21" in today_df.columns else current_price

                # Must be above VWAP and all MAs
                if pd.isna(vwap) or pd.isna(ema_9) or pd.isna(ema_21):
                    continue
                if not (current_price > float(vwap) and
                        current_price > float(ema_9) and
                        current_price > float(ema_21)):
                    continue

                entry = current_price
                stop = entry * (1 - STOP_PCT)
                # Target: +3% from entry (momentum continuation)
                target = entry * 1.03

                conviction = 2  # overnight is inherently higher conviction
                if pct_change > 5:
                    conviction += 1
                if rvol > 4:
                    conviction += 1

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction="long",
                    entry_price=round(entry, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"day_gain={pct_change:.1f}% rvol={rvol:.1f} above_vwap=True",
                ))
                logger.debug(f"OvernightSwing: {symbol} long {pct_change:.1f}% day gain")

            except Exception as exc:
                logger.warning(f"OvernightSwing {symbol}: {exc}")

        return signals
