"""
Technical indicators — pure functions operating on OHLCV DataFrames.
Uses pandas-ta for core calculations.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd
import pandas_ta as ta
from loguru import logger


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add intraday VWAP column.
    Resets at market open each day using cumulative typical_price * volume.
    """
    df = df.copy()
    typical = (df["high"] + df["low"] + df["close"]) / 3
    df["tp_vol"] = typical * df["volume"]

    # group by date to reset daily
    if hasattr(df.index, "date"):
        dates = df.index.date if not hasattr(df.index, "tz") or df.index.tz is None \
            else df.index.tz_localize(None).normalize()
        df["_date"] = df.index.date
    else:
        df["_date"] = pd.to_datetime(df.index).date

    df["cum_tp_vol"] = df.groupby("_date")["tp_vol"].cumsum()
    df["cum_vol"] = df.groupby("_date")["volume"].cumsum()
    df["vwap"] = df["cum_tp_vol"] / df["cum_vol"]
    df.drop(columns=["tp_vol", "cum_tp_vol", "cum_vol", "_date"], inplace=True)
    return df


def add_ema(df: pd.DataFrame, fast: int = 9, slow: int = 21) -> pd.DataFrame:
    """Add EMA fast and slow columns using pandas-ta."""
    df = df.copy()
    df[f"ema_{fast}"] = ta.ema(df["close"], length=fast)
    df[f"ema_{slow}"] = ta.ema(df["close"], length=slow)
    return df


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add RSI column using pandas-ta."""
    df = df.copy()
    df["rsi"] = ta.rsi(df["close"], length=period)
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ATR column using pandas-ta."""
    df = df.copy()
    atr_result = ta.atr(df["high"], df["low"], df["close"], length=period)
    df["atr"] = atr_result
    return df


def add_rvol(df: pd.DataFrame, lookback_days: int = 10) -> pd.DataFrame:
    """
    Add relative volume column.
    For each bar: volume / avg_volume_at_same_bar_time over past lookback_days.
    For daily bars this is simply volume / rolling_mean(volume).
    """
    df = df.copy()
    avg_vol = df["volume"].rolling(window=lookback_days, min_periods=1).mean()
    df["rvol"] = df["volume"] / avg_vol.replace(0, np.nan)
    df["rvol"] = df["rvol"].fillna(1.0)
    return df


def opening_range(df: pd.DataFrame, minutes: int = 15) -> Tuple[float, float]:
    """
    Return (or_high, or_low) from the first `minutes` minutes of the trading day.
    df should be a minute-bar DataFrame for a single trading day, index in ET.
    """
    try:
        import pytz
        ET = pytz.timezone("America/New_York")
        df_et = df.copy()
        if df_et.index.tz is None:
            df_et.index = df_et.index.tz_localize("UTC").tz_convert(ET)
        else:
            df_et.index = df_et.index.tz_convert(ET)

        # Find the open bar (9:30 ET)
        open_bars = df_et.between_time("09:30", "09:44")
        if len(open_bars) == 0:
            # Fallback: first `minutes` bars
            open_bars = df_et.head(minutes)

        or_high = float(open_bars["high"].max())
        or_low = float(open_bars["low"].min())
        return or_high, or_low
    except Exception as exc:
        logger.warning(f"opening_range: {exc}")
        if len(df) == 0:
            return 0.0, 0.0
        return float(df["high"].max()), float(df["low"].min())
