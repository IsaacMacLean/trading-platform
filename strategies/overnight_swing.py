"""
Overnight Swing Strategy.
Only takes the strongest setups: up >3% on day, RVOL>3, above VWAP+MAs,
RSI in healthy range (45-68), near HOD.  1 overnight position max.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

import pytz
from loguru import logger

from strategies.base import BaseStrategy, Signal
from data.indicators import add_vwap, add_ema, add_rsi
import config


def _has_earnings_soon(symbol: str) -> bool:
    """
    Returns True if the stock reports earnings within the next 2 trading days.
    Holding through earnings overnight is gambling — skip these setups.
    """
    try:
        import yfinance as yf
        from datetime import timedelta
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return False
        today = datetime.now(ET).date()
        cutoff = today + timedelta(days=2)
        # Newer yfinance returns a dict
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            for d in (dates if hasattr(dates, "__iter__") else [dates]):
                if hasattr(d, "date"):
                    d = d.date()
                if today <= d <= cutoff:
                    return True
            return False
        # Older yfinance returns a DataFrame
        if hasattr(cal, "loc"):
            try:
                ed = cal.loc["Earnings Date"]
                for d in (ed if hasattr(ed, "__iter__") else [ed]):
                    if hasattr(d, "date"):
                        d = d.date()
                    if today <= d <= cutoff:
                        return True
            except Exception:
                pass
        return False
    except Exception:
        return False  # fail-safe: if we can't check, allow the trade

ET = pytz.timezone("America/New_York")
MIN_UP_PCT = 3.0
MIN_RVOL = 3.0           # raised from 2.0 — stronger volume confirmation required
STOP_PCT = 0.025         # 2.5% stop (was 2%)  — give overnight room
TARGET_PCT = 0.05        # 5% target (was 3%)  — better R:R for overnight risk
RSI_MIN = 45             # healthy momentum floor — not just bouncing dead cat
RSI_MAX = 68             # not overbought — room left to run
HOD_PROXIMITY_PCT = 0.03 # must be within 3% of day's high — strong tape


class OvernightSwing(BaseStrategy):
    """
    Hold high-quality momentum stocks overnight for gap-up continuation.
    Higher standards than intraday: requires multiple confirming conditions.
    """

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

            # Skip if earnings are within 2 days — overnight holds through earnings = gambling
            if _has_earnings_soon(symbol):
                logger.info(f"OvernightSwing {symbol}: earnings soon — skipping")
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
                today_df = add_rsi(today_df, period=14)

                current_price = float(today_df["close"].iloc[-1])
                open_price = float(today_df["open"].iloc[0])
                day_high = float(today_df["high"].max())

                pct_change = (current_price - open_price) / open_price * 100
                if pct_change < MIN_UP_PCT:
                    continue

                # Must be near high of day — strong close matters most
                dist_from_hod = (day_high - current_price) / day_high
                if dist_from_hod > HOD_PROXIMITY_PCT:
                    logger.debug(f"OvernightSwing {symbol}: too far from HOD ({dist_from_hod*100:.1f}%)")
                    continue

                vwap = today_df["vwap"].iloc[-1] if "vwap" in today_df.columns else current_price
                ema_9 = today_df["ema_9"].iloc[-1] if "ema_9" in today_df.columns else current_price
                ema_21 = today_df["ema_21"].iloc[-1] if "ema_21" in today_df.columns else current_price
                rsi_val = today_df["rsi"].iloc[-1] if "rsi" in today_df.columns else 55.0

                if pd.isna(vwap) or pd.isna(ema_9) or pd.isna(ema_21) or pd.isna(rsi_val):
                    continue

                rsi = float(rsi_val)

                # Must be in healthy RSI range — not overbought, not just a dead-cat bounce
                if not (RSI_MIN <= rsi <= RSI_MAX):
                    logger.debug(f"OvernightSwing {symbol}: RSI {rsi:.0f} outside [{RSI_MIN}-{RSI_MAX}]")
                    continue

                # Must be above VWAP and both MAs — strong tape
                if not (current_price > float(vwap) and
                        current_price > float(ema_9) and
                        current_price > float(ema_21)):
                    continue

                entry = current_price
                stop = entry * (1 - STOP_PCT)
                target = entry * (1 + TARGET_PCT)

                conviction = 2  # overnight carries inherent higher bar
                if pct_change > 5:
                    conviction += 1
                if rvol > 5:
                    conviction += 1
                if rsi > 55:
                    conviction += 1  # strong momentum confirmed by RSI

                signals.append(Signal(
                    symbol=symbol,
                    strategy=self.name,
                    direction="long",
                    entry_price=round(entry, 2),
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    conviction=conviction,
                    notes=f"day_gain={pct_change:.1f}% rvol={rvol:.1f} rsi={rsi:.0f} above_vwap=True dist_hod={dist_from_hod*100:.1f}%",
                ))
                logger.debug(f"OvernightSwing: {symbol} {pct_change:.1f}% gain, RSI={rsi:.0f}, RVOL={rvol:.1f}")

            except Exception as exc:
                logger.warning(f"OvernightSwing {symbol}: {exc}")

        return signals
