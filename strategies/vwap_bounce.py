"""
VWAP Bounce Strategy.
Spec: Within 0.1% of VWAP, stop 0.3% through VWAP, target prev high/low.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal
from data.indicators import add_vwap, add_ema

ET = pytz.timezone("America/New_York")
ENTRY_BAND_PCT = 0.001   # 0.1% from VWAP
STOP_THROUGH_PCT = 0.003  # 0.3% through VWAP
POSITION_SIZE_PCT = 0.125  # 12.5% midpoint of 10-15%


class VWAPBounce(BaseStrategy):
    """
    Buy pullbacks to VWAP in uptrends.
    Short rallies to VWAP in downtrends.
    Active 10:00 AM – 2:00 PM.
    """

    name = "vwap_bounce"

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        signals: List[Signal] = []
        now_et = datetime.now(ET)
        market_minutes = now_et.hour * 60 + now_et.minute

        # 10:00 AM to 2:00 PM ET
        if not (10 * 60 <= market_minutes <= 14 * 60):
            return signals

        for item in watchlist:
            symbol = item.get("symbol", "")

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

                if "vwap" not in today_df.columns or today_df["vwap"].isna().all():
                    continue

                current_price = float(today_df["close"].iloc[-1])
                vwap = float(today_df["vwap"].iloc[-1])
                ema_9 = today_df.get("ema_9", today_df["close"]).iloc[-1]
                ema_21 = today_df.get("ema_21", today_df["close"]).iloc[-1]

                if vwap == 0:
                    continue

                distance_pct = abs(current_price - vwap) / vwap

                if distance_pct > ENTRY_BAND_PCT:
                    continue

                # Trend determination
                above_vwap = current_price > vwap
                in_uptrend = (
                    pd.notna(ema_9) and pd.notna(ema_21) and float(ema_9) > float(ema_21)
                )
                in_downtrend = (
                    pd.notna(ema_9) and pd.notna(ema_21) and float(ema_9) < float(ema_21)
                )

                # Day high/low for targets
                day_high = float(today_df["high"].max())
                day_low = float(today_df["low"].min())

                if in_uptrend and not above_vwap:
                    # Pullback to VWAP in uptrend — long
                    direction = "long"
                    entry = current_price
                    stop = vwap * (1 - STOP_THROUGH_PCT)
                    target = day_high
                elif in_downtrend and above_vwap:
                    # Rally to VWAP in downtrend — short
                    direction = "short"
                    entry = current_price
                    stop = vwap * (1 + STOP_THROUGH_PCT)
                    target = day_low
                else:
                    continue

                conviction = 1
                rvol = item.get("rvol", 1.0)
                if rvol > 3:
                    conviction += 1

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction=direction,
                    entry_price=round(entry, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"vwap={vwap:.2f} dist={distance_pct*100:.3f}% trend={'up' if in_uptrend else 'down'}",
                ))
                logger.debug(f"VWAPBounce: {symbol} {direction} price={current_price:.2f} vwap={vwap:.2f}")

            except Exception as exc:
                logger.warning(f"VWAPBounce {symbol}: {exc}")

        return signals
