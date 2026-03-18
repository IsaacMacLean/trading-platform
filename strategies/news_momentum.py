"""
News & Volume Momentum Strategy.
Spec: RVOL>5, price accelerating over 5 bars, 1.5% trailing stop, RSI filter.
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
MIN_RVOL = 5.0
EXIT_RVOL = 2.0
TRAIL_STOP_PCT = config.MOMENTUM_TRAIL_PCT  # 1.5% (was 1%)


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

        # 9:30 AM to 3:30 PM (give last 30 min liquidity for exit)
        if not (9 * 60 + 30 <= market_minutes <= 15 * 60 + 30):
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
                if len(today_df) < 8:
                    continue

                # RSI filter
                today_df = add_rsi(today_df, period=14)
                rsi_val = today_df["rsi"].iloc[-1] if "rsi" in today_df.columns else 50.0
                if pd.isna(rsi_val):
                    rsi_val = 50.0
                rsi = float(rsi_val)

                current_price = float(today_df["close"].iloc[-1])
                open_price = float(today_df["open"].iloc[0])
                direction = "long" if current_price >= open_price else "short"

                # RSI guard
                if direction == "long" and rsi > config.RSI_OVERBOUGHT:
                    logger.debug(f"NewsMomentum {symbol} long skipped: RSI {rsi:.0f}")
                    continue
                if direction == "short" and rsi < config.RSI_OVERSOLD:
                    logger.debug(f"NewsMomentum {symbol} short skipped: RSI {rsi:.0f}")
                    continue

                # Price acceleration over last 5 bars (stronger confirmation than 3)
                recent = today_df.tail(5)
                price_momentum = float(recent["close"].iloc[-1]) - float(recent["close"].iloc[0])
                if direction == "long" and price_momentum <= 0:
                    continue
                if direction == "short" and price_momentum >= 0:
                    continue

                if direction == "long":
                    stop = current_price * (1 - TRAIL_STOP_PCT)
                    target = current_price * (1 + TRAIL_STOP_PCT * 2)  # 2:1 R:R
                else:
                    stop = current_price * (1 + TRAIL_STOP_PCT)
                    target = current_price * (1 - TRAIL_STOP_PCT * 2)

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
                    notes=f"rvol={rvol:.1f} rsi={rsi:.0f} trail={TRAIL_STOP_PCT*100:.1f}%",
                ))
                logger.debug(f"NewsMomentum: {symbol} {direction} rvol={rvol:.1f} rsi={rsi:.0f}")

            except Exception as exc:
                logger.warning(f"NewsMomentum {symbol}: {exc}")

        return signals
