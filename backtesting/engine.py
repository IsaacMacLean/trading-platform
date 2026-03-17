"""
BacktestEngine — minute-bar backtesting using yfinance data.
Simulates realistic execution: 1-bar lag, slippage, no commission.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytz
import yfinance as yf
from loguru import logger

import config

ET = pytz.timezone("America/New_York")


@dataclass
class BacktestTrade:
    symbol: str
    strategy: str
    direction: str
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    qty: int = 0
    stop_price: float = 0.0
    target_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_minutes: float = 0.0


def _fetch_yfinance_minute_bars(symbol: str, days: int = 30) -> pd.DataFrame:
    """Download 1-minute bars from yfinance for backtesting."""
    try:
        end = datetime.now()
        start = end - timedelta(days=days + 5)
        ticker = yf.Ticker(symbol)
        # yfinance max 7 days for 1m; use 1h for longer windows, 1m for short
        if days <= 7:
            df = ticker.history(interval="1m", start=start, end=end)
        else:
            df = ticker.history(interval="1h", start=start, end=end)
        df.index = pd.to_datetime(df.index, utc=True)
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as exc:
        logger.error(f"yfinance {symbol}: {exc}")
        return pd.DataFrame()


def _apply_slippage(price: float, direction: str, symbol: str = "") -> float:
    """Apply realistic slippage to a fill price."""
    slippage = config.SLIPPAGE_LIQUID
    if direction == "long":
        return price * (1 + slippage)
    else:
        return price * (1 - slippage)


class BacktestEngine:
    """
    Minute-bar backtester.
    Runs each strategy against historical data and returns trades + equity curve.
    """

    def __init__(
        self,
        symbols: List[str],
        days: int = 30,
        initial_equity: float = 100_000.0,
    ):
        self.symbols = symbols
        self.days = days
        self.initial_equity = initial_equity
        self._data: Dict[str, pd.DataFrame] = {}

    def _load_data(self) -> None:
        """Pre-load minute bar data for all symbols."""
        logger.info(f"Loading backtest data for {len(self.symbols)} symbols over {self.days} days...")
        for sym in self.symbols:
            df = _fetch_yfinance_minute_bars(sym, self.days)
            if not df.empty:
                self._data[sym] = df
                logger.debug(f"  {sym}: {len(df)} bars")
            else:
                logger.warning(f"  {sym}: no data")

    def run_strategy_backtest(
        self,
        strategy_name: str,
        signals_by_date: Dict[str, List[dict]],
    ) -> Tuple[List[BacktestTrade], pd.Series]:
        """
        Generic backtester given a dict of {date_str: [signal_dicts]}.
        Each signal dict: {symbol, direction, entry_price, stop_price, target_price, qty}.

        Returns (trades_list, equity_curve_series).
        """
        equity = self.initial_equity
        trades: List[BacktestTrade] = []
        equity_curve = []

        all_dates = sorted(set(
            df.index.date
            for df in self._data.values()
            for _ in [None]
        ) if self._data else [])

        for trade_date in all_dates:
            date_str = trade_date.isoformat()
            day_signals = signals_by_date.get(date_str, [])

            for sig in day_signals:
                sym = sig.get("symbol", "")
                direction = sig.get("direction", "long")
                entry_target = sig.get("entry_price", 0.0)
                stop = sig.get("stop_price", 0.0)
                target = sig.get("target_price", 0.0)
                qty = sig.get("qty", 0)

                if sym not in self._data or qty == 0:
                    continue

                df = self._data[sym]
                df_et = df.copy()
                df_et.index = df_et.index.tz_convert(ET)
                day_df = df_et[df_et.index.date == trade_date]

                if day_df.empty:
                    continue

                # Find entry: 1 bar after signal (execution lag)
                entry_bars = day_df[day_df["close"] >= entry_target] if direction == "long" \
                    else day_df[day_df["close"] <= entry_target]

                if entry_bars.empty:
                    continue

                entry_idx = day_df.index.get_loc(entry_bars.index[0])
                if entry_idx + 1 >= len(day_df):
                    continue

                entry_bar = day_df.iloc[entry_idx + 1]
                fill_price = _apply_slippage(float(entry_bar["open"]), direction, sym)
                entry_time = entry_bar.name

                # Simulate trade through remaining bars
                exit_price = None
                exit_time = None
                exit_reason = "eod"

                for _, bar in day_df.iloc[entry_idx + 2:].iterrows():
                    bar_high = float(bar["high"])
                    bar_low = float(bar["low"])
                    bar_close = float(bar["close"])

                    if direction == "long":
                        if stop > 0 and bar_low <= stop:
                            exit_price = stop
                            exit_time = bar.name
                            exit_reason = "stop"
                            break
                        if target > 0 and bar_high >= target:
                            exit_price = target
                            exit_time = bar.name
                            exit_reason = "target"
                            break
                    else:
                        if stop > 0 and bar_high >= stop:
                            exit_price = stop
                            exit_time = bar.name
                            exit_reason = "stop"
                            break
                        if target > 0 and bar_low <= target:
                            exit_price = target
                            exit_time = bar.name
                            exit_reason = "target"
                            break

                if exit_price is None:
                    # EOD close
                    last_bar = day_df.iloc[-1]
                    exit_price = float(last_bar["close"])
                    exit_time = last_bar.name
                    exit_reason = "eod"

                exit_price = _apply_slippage(exit_price, "short" if direction == "long" else "long", sym)

                if direction == "long":
                    pnl = (exit_price - fill_price) * qty
                else:
                    pnl = (fill_price - exit_price) * qty

                pnl_pct = pnl / (fill_price * qty) if fill_price > 0 and qty > 0 else 0.0
                hold_min = (exit_time - entry_time).total_seconds() / 60 if exit_time else 0

                trade = BacktestTrade(
                    symbol=sym,
                    strategy=strategy_name,
                    direction=direction,
                    entry_time=entry_time,
                    entry_price=fill_price,
                    exit_time=exit_time,
                    exit_price=exit_price,
                    qty=qty,
                    stop_price=stop,
                    target_price=target,
                    exit_reason=exit_reason,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    hold_minutes=hold_min,
                )
                trades.append(trade)
                equity += pnl

            equity_curve.append((trade_date, equity))

        equity_series = pd.Series(
            [e for _, e in equity_curve],
            index=pd.DatetimeIndex([pd.Timestamp(d) for d, _ in equity_curve]),
            name="equity",
        )
        return trades, equity_series

    def run_momentum_backtest(self) -> Tuple[List[BacktestTrade], pd.Series]:
        """
        Simplified momentum backtest: buy on days where stock is up >2% from prior close,
        exit EOD. Uses 1-bar lag and slippage.
        """
        if not self._data:
            self._load_data()

        equity = self.initial_equity
        trades: List[BacktestTrade] = []
        equity_points = []

        # Get all trading dates from SPY or first available symbol
        ref_symbol = "SPY" if "SPY" in self._data else (list(self._data.keys())[0] if self._data else None)
        if ref_symbol is None:
            return trades, pd.Series(dtype=float)

        ref_df = self._data[ref_symbol]
        ref_df_et = ref_df.copy()
        ref_df_et.index = ref_df_et.index.tz_convert(ET)
        all_dates = sorted(set(ref_df_et.index.date))

        for trade_date in all_dates:
            day_pnl = 0.0

            for sym, df in self._data.items():
                df_et = df.copy()
                df_et.index = df_et.index.tz_convert(ET)
                day_df = df_et[df_et.index.date == trade_date]
                if len(day_df) < 5:
                    continue

                # Get prior close
                prior_days = df_et[df_et.index.date < trade_date]
                if prior_days.empty:
                    continue
                prior_close = float(prior_days["close"].iloc[-1])
                open_price = float(day_df["open"].iloc[0])

                gap_pct = (open_price - prior_close) / prior_close * 100
                if gap_pct < 2.0:
                    continue

                # Simulate: enter at bar 1 (1-bar lag), exit EOD
                if len(day_df) < 3:
                    continue

                fill = _apply_slippage(float(day_df["open"].iloc[1]), "long", sym)
                exit_p = _apply_slippage(float(day_df["close"].iloc[-1]), "short", sym)
                alloc = equity * 0.10  # 10% per position
                qty = max(1, int(alloc / fill)) if fill > 0 else 0
                if qty == 0:
                    continue

                pnl = (exit_p - fill) * qty
                day_pnl += pnl

                trades.append(BacktestTrade(
                    symbol=sym,
                    strategy="momentum_backtest",
                    direction="long",
                    entry_time=day_df.index[1],
                    entry_price=fill,
                    exit_time=day_df.index[-1],
                    exit_price=exit_p,
                    qty=qty,
                    exit_reason="eod",
                    pnl=pnl,
                    pnl_pct=(exit_p - fill) / fill if fill > 0 else 0,
                    hold_minutes=len(day_df),
                ))

            equity += day_pnl
            equity_points.append((trade_date, equity))

        equity_series = pd.Series(
            [e for _, e in equity_points],
            index=pd.DatetimeIndex([pd.Timestamp(d) for d, _ in equity_points]),
            name="equity",
        )
        return trades, equity_series

    def run(self) -> dict:
        """Run full backtest and return results dict."""
        self._load_data()
        trades, equity_curve = self.run_momentum_backtest()

        trades_df = pd.DataFrame([
            {
                "symbol": t.symbol,
                "strategy": t.strategy,
                "direction": t.direction,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "qty": t.qty,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "hold_minutes": t.hold_minutes,
                "exit_reason": t.exit_reason,
            }
            for t in trades
        ]) if trades else pd.DataFrame()

        return {
            "trades": trades_df,
            "equity_curve": equity_curve,
            "initial_equity": self.initial_equity,
            "final_equity": float(equity_curve.iloc[-1]) if not equity_curve.empty else self.initial_equity,
        }
