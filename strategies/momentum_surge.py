"""
Momentum Surge Strategy.
Spec: >2% in 5 min on 7x volume, 1.5% trailing stop, RSI filter.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal
from data.indicators import add_rsi
import config

ET = pytz.timezone("America/New_York")
SURGE_PCT = 2.0              # raised from 1.5% — require stronger move
SURGE_VOL_MULTIPLIER = 7.0   # raised from 5x — require conviction volume
TRAILING_STOP_PCT = config.MOMENTUM_TRAIL_PCT  # 1.5% (was 0.5% — way too tight)
MAX_HOLD_MINUTES = 120


class MomentumSurge(BaseStrategy):
    """Ride intraday momentum surges on huge volume."""

    name = "momentum_surge"

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        signals: List[Signal] = []
        now_et = datetime.now(ET)
        market_minutes = now_et.hour * 60 + now_et.minute

        # Active 9:45 AM to 3:00 PM (avoid last 30 min choppiness)
        if not (9 * 60 + 45 <= market_minutes <= 15 * 60):
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
                if len(today_df) < 10:
                    continue

                # RSI filter — avoid buying overbought or shorting oversold
                today_df = add_rsi(today_df, period=14)
                rsi = float(today_df["rsi"].iloc[-1]) if "rsi" in today_df.columns and not pd.isna(today_df["rsi"].iloc[-1]) else 50.0

                current_price = float(today_df["close"].iloc[-1])
                price_5min_ago = float(today_df["close"].iloc[max(0, len(today_df) - 6)])
                pct_change_5m = (current_price - price_5min_ago) / price_5min_ago * 100

                if abs(pct_change_5m) < SURGE_PCT:
                    continue

                direction = "long" if pct_change_5m > 0 else "short"

                # RSI guard: don't chase already-extended moves
                if direction == "long" and rsi > config.RSI_OVERBOUGHT:
                    logger.debug(f"MomentumSurge {symbol} long skipped: RSI {rsi:.0f} overbought")
                    continue
                if direction == "short" and rsi < config.RSI_OVERSOLD:
                    logger.debug(f"MomentumSurge {symbol} short skipped: RSI {rsi:.0f} oversold")
                    continue

                # Volume check: recent 5 bars vs prior bars today
                recent_vol = float(today_df["volume"].iloc[-6:].mean())
                prior_vol = float(today_df["volume"].iloc[:-6].mean()) if len(today_df) > 12 else recent_vol
                vol_ratio = recent_vol / prior_vol if prior_vol > 0 else 1.0

                if vol_ratio < SURGE_VOL_MULTIPLIER:
                    continue

                if direction == "long":
                    entry = current_price
                    stop = current_price * (1 - TRAILING_STOP_PCT)
                    target = current_price * 1.03  # 2:1 on 1.5% stop
                else:
                    entry = current_price
                    stop = current_price * (1 + TRAILING_STOP_PCT)
                    target = current_price * 0.97

                conviction = 1
                if rvol > 5:
                    conviction += 1
                if abs(pct_change_5m) > 3.5:
                    conviction += 1
                if vol_ratio > 10:
                    conviction += 1

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction=direction,
                    entry_price=round(entry, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"surge={pct_change_5m:.1f}% vol={vol_ratio:.1f}x rvol={rvol:.1f} rsi={rsi:.0f}",
                ))
                logger.debug(f"MomentumSurge: {symbol} {direction} {pct_change_5m:.1f}% vol={vol_ratio:.0f}x rsi={rsi:.0f}")

            except Exception as exc:
                logger.warning(f"MomentumSurge {symbol}: {exc}")

        return signals
