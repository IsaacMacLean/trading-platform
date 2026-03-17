import pandas as pd
import pandas_ta as ta

from config import EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_THRESHOLD, ATR_PERIOD


def compute_signals(df: pd.DataFrame) -> dict:
    """
    Dual EMA crossover with RSI momentum filter.

    Entry:  fast EMA crosses above slow EMA AND RSI > RSI_THRESHOLD
    Exit:   fast EMA crosses below slow EMA

    Returns a dict with keys:
        signal  - "buy", "sell", or None
        close   - latest close price
        atr     - latest ATR value
        rsi     - latest RSI value
        ema_fast, ema_slow - latest EMA values
    """
    min_bars = EMA_SLOW + ATR_PERIOD + 5
    if len(df) < min_bars:
        return {"signal": None}

    close = df["close"]
    high = df["high"]
    low = df["low"]

    ema_fast = ta.ema(close, length=EMA_FAST)
    ema_slow = ta.ema(close, length=EMA_SLOW)
    rsi = ta.rsi(close, length=RSI_PERIOD)
    atr = ta.atr(high, low, close, length=ATR_PERIOD)

    if any(x is None or x.dropna().empty for x in [ema_fast, ema_slow, rsi, atr]):
        return {"signal": None}

    prev_fast, curr_fast = ema_fast.iloc[-2], ema_fast.iloc[-1]
    prev_slow, curr_slow = ema_slow.iloc[-2], ema_slow.iloc[-1]
    curr_rsi = rsi.iloc[-1]
    curr_atr = atr.iloc[-1]
    curr_close = close.iloc[-1]

    bullish_cross = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
    bearish_cross = (prev_fast >= prev_slow) and (curr_fast < curr_slow)

    signal = None
    if bullish_cross and curr_rsi > RSI_THRESHOLD:
        signal = "buy"
    elif bearish_cross:
        signal = "sell"

    return {
        "signal": signal,
        "close": curr_close,
        "atr": curr_atr,
        "rsi": curr_rsi,
        "ema_fast": curr_fast,
        "ema_slow": curr_slow,
    }
