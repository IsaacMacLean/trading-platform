"""
AlpacaFetcher — real-time and historical data via alpaca-py.
"""
from __future__ import annotations

import pytz
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

ET = pytz.timezone("America/New_York")
UTC = pytz.UTC


def _df_from_bars(bars, symbol: str) -> pd.DataFrame:
    """Extract a clean DataFrame from alpaca-py bar response."""
    df = bars.df
    if df.empty:
        return df
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")
    df.index = pd.to_datetime(df.index, utc=True)
    df.rename(columns={"open": "open", "high": "high", "low": "low",
                        "close": "close", "volume": "volume",
                        "trade_count": "trade_count", "vwap": "vwap"}, inplace=True)
    return df


class AlpacaFetcher:
    """Fetches market data from Alpaca."""

    def __init__(self):
        self.trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        self.data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        # Cache daily EMA results for 2 hours — daily bars don't change intraday
        self._ema_cache: Dict[str, tuple] = {}  # symbol -> (timestamp, above_ema: bool)

    # ------------------------------------------------------------------
    # Daily bars
    # ------------------------------------------------------------------

    def get_daily_bars(self, symbol: str, days: int = 60) -> pd.DataFrame:
        """Return daily OHLCV DataFrame for the past `days` calendar days."""
        end = datetime.now(UTC)
        start = end - timedelta(days=days + 10)  # buffer for weekends/holidays
        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                feed=DataFeed.IEX,
            )
            bars = self.data_client.get_stock_bars(req)
            df = _df_from_bars(bars, symbol)
            return df.tail(days)
        except Exception as exc:
            logger.error(f"get_daily_bars({symbol}): {exc}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Minute bars
    # ------------------------------------------------------------------

    def get_minute_bars(self, symbol: str, days: int = 5) -> pd.DataFrame:
        """Return 1-minute OHLCV DataFrame for the past `days` trading days."""
        end = datetime.now(UTC)
        start = end - timedelta(days=days + 4)  # buffer for weekends
        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(1, TimeFrameUnit.Minute),
                start=start,
                end=end,
                feed=DataFeed.IEX,
            )
            bars = self.data_client.get_stock_bars(req)
            df = _df_from_bars(bars, symbol)
            return df
        except Exception as exc:
            logger.error(f"get_minute_bars({symbol}): {exc}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Premarket snapshot
    # ------------------------------------------------------------------

    def get_premarket_snapshot(self, symbols: List[str]) -> Dict[str, dict]:
        """
        Return latest bar/quote data for a list of symbols.
        Result: {symbol: {"close": ..., "volume": ..., "prev_close": ...}}
        """
        result: Dict[str, dict] = {}
        if not symbols:
            return result

        try:
            bar_req = StockLatestBarRequest(symbol_or_symbols=symbols, feed=DataFeed.IEX)
            latest_bars = self.data_client.get_stock_latest_bar(bar_req)
        except Exception as exc:
            logger.error(f"get_premarket_snapshot bars: {exc}")
            latest_bars = {}

        for symbol in symbols:
            try:
                bar = latest_bars.get(symbol)
                if bar is None:
                    continue
                # get previous close from daily bars
                daily = self.get_daily_bars(symbol, days=5)
                if daily.empty or len(daily) < 2:
                    prev_close = float(bar.close)
                else:
                    prev_close = float(daily["close"].iloc[-2])

                result[symbol] = {
                    "close": float(bar.close),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "volume": float(bar.volume),
                    "prev_close": prev_close,
                    "gap_pct": (float(bar.close) - prev_close) / prev_close * 100
                    if prev_close
                    else 0.0,
                }
            except Exception as exc:
                logger.warning(f"Snapshot for {symbol}: {exc}")

        return result

    # ------------------------------------------------------------------
    # Relative volume
    # ------------------------------------------------------------------

    def is_above_daily_ema(self, symbol: str, period: int = 20) -> bool:
        """
        Returns True if the stock's latest close is above its N-day EMA.
        Cached per session (2-hour TTL) — daily bars don't move intraday.
        Fail-open: returns True if data is unavailable so we don't block signals.
        """
        import time as _time
        now_ts = _time.time()
        cached = self._ema_cache.get(symbol)
        if cached and (now_ts - cached[0]) < 7200:
            return cached[1]
        try:
            import pandas_ta as ta
            df = self.get_daily_bars(symbol, days=period + 10)
            if df.empty or len(df) < period:
                self._ema_cache[symbol] = (now_ts, True)
                return True
            ema = ta.ema(df["close"], length=period)
            if ema is None or ema.isna().all():
                self._ema_cache[symbol] = (now_ts, True)
                return True
            current = float(df["close"].iloc[-1])
            ema_val = float(ema.iloc[-1])
            result = current > ema_val
            self._ema_cache[symbol] = (now_ts, result)
            return result
        except Exception as exc:
            logger.warning(f"is_above_daily_ema({symbol}): {exc}")
            return True  # fail open

    def get_rvol(self, symbol: str) -> float:
        """
        Relative volume: current bar's volume vs average volume at this
        time of day over the past 10 trading days.
        """
        try:
            df = self.get_minute_bars(symbol, days=12)
            if df.empty:
                return 1.0

            now_et = datetime.now(ET)
            current_minute = now_et.hour * 60 + now_et.minute

            df_et = df.copy()
            df_et.index = df_et.index.tz_convert(ET)
            df_et["tod_min"] = df_et.index.hour * 60 + df_et.index.minute

            # today's cumulative volume up to this minute
            today_str = now_et.date()
            today_mask = df_et.index.date == today_str
            today_df = df_et[today_mask]
            if today_df.empty:
                return 1.0
            current_vol = float(today_df["volume"].sum())

            # historical average cumulative volume at this time of day
            past_mask = df_et.index.date < today_str
            past_df = df_et[past_mask]
            if past_df.empty:
                return 1.0

            daily_vols = []
            for date, grp in past_df.groupby(past_df.index.date):
                cum_vol = float(grp[grp["tod_min"] <= current_minute]["volume"].sum())
                if cum_vol > 0:
                    daily_vols.append(cum_vol)

            if not daily_vols:
                return 1.0

            avg_vol = sum(daily_vols) / len(daily_vols)
            return current_vol / avg_vol if avg_vol > 0 else 1.0

        except Exception as exc:
            logger.error(f"get_rvol({symbol}): {exc}")
            return 1.0
