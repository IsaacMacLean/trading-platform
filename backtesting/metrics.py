"""
Backtesting metrics — short-term focused performance analysis.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd


def compute_metrics(
    trades_df: pd.DataFrame,
    equity_curve: pd.Series,
    initial_equity: float = 100_000.0,
) -> Dict:
    """
    Compute comprehensive performance metrics from trades and equity curve.

    Returns a dict with all key metrics.
    """
    metrics: Dict = {}

    # -----------------------------------------------------------------------
    # Basic trade stats
    # -----------------------------------------------------------------------
    if trades_df is None or trades_df.empty:
        metrics["total_trades"] = 0
        metrics["win_rate"] = 0.0
        metrics["total_pnl"] = 0.0
        metrics["total_pnl_pct"] = 0.0
        return metrics

    df = trades_df.copy()
    metrics["total_trades"] = len(df)
    metrics["trades_per_day"] = 0.0

    if "entry_time" in df.columns and df["entry_time"].notna().any():
        try:
            days = (pd.to_datetime(df["entry_time"]).max() -
                    pd.to_datetime(df["entry_time"]).min()).days or 1
            metrics["trades_per_day"] = round(len(df) / max(days, 1), 2)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # P&L
    # -----------------------------------------------------------------------
    if "pnl" in df.columns:
        total_pnl = float(df["pnl"].sum())
    else:
        total_pnl = 0.0

    metrics["total_pnl"] = round(total_pnl, 2)
    metrics["total_pnl_pct"] = round(total_pnl / initial_equity * 100, 2)

    # Winners / losers
    winners = df[df["pnl"] > 0] if "pnl" in df.columns else pd.DataFrame()
    losers = df[df["pnl"] < 0] if "pnl" in df.columns else pd.DataFrame()

    metrics["num_wins"] = len(winners)
    metrics["num_losses"] = len(losers)
    metrics["win_rate"] = round(len(winners) / len(df) * 100, 1) if len(df) > 0 else 0.0

    metrics["avg_win"] = round(float(winners["pnl"].mean()), 2) if not winners.empty else 0.0
    metrics["avg_loss"] = round(float(losers["pnl"].mean()), 2) if not losers.empty else 0.0
    metrics["largest_win"] = round(float(winners["pnl"].max()), 2) if not winners.empty else 0.0
    metrics["largest_loss"] = round(float(losers["pnl"].min()), 2) if not losers.empty else 0.0

    # Profit factor
    gross_profit = float(winners["pnl"].sum()) if not winners.empty else 0.0
    gross_loss = abs(float(losers["pnl"].sum())) if not losers.empty else 0.0
    metrics["profit_factor"] = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    # Expectancy
    metrics["expectancy"] = round(
        (metrics["avg_win"] * len(winners) + metrics["avg_loss"] * len(losers)) / len(df), 2
    ) if len(df) > 0 else 0.0

    # -----------------------------------------------------------------------
    # Hold time
    # -----------------------------------------------------------------------
    if "hold_minutes" in df.columns:
        metrics["avg_hold_minutes"] = round(float(df["hold_minutes"].mean()), 1)
        metrics["max_hold_minutes"] = round(float(df["hold_minutes"].max()), 1)
    else:
        metrics["avg_hold_minutes"] = 0.0
        metrics["max_hold_minutes"] = 0.0

    # -----------------------------------------------------------------------
    # Equity curve metrics
    # -----------------------------------------------------------------------
    if equity_curve is not None and not equity_curve.empty:
        equity = equity_curve.copy()

        # Daily returns
        daily_returns = equity.pct_change().dropna()

        # Max drawdown
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max
        metrics["max_drawdown_pct"] = round(float(drawdown.min()) * 100, 2)

        # Max intraday drawdown (using daily returns as proxy)
        metrics["max_intraday_drawdown_pct"] = metrics["max_drawdown_pct"]

        # Best / worst day
        if not daily_returns.empty:
            metrics["best_day_pct"] = round(float(daily_returns.max()) * 100, 2)
            metrics["worst_day_pct"] = round(float(daily_returns.min()) * 100, 2)
        else:
            metrics["best_day_pct"] = 0.0
            metrics["worst_day_pct"] = 0.0

        # Sharpe ratio (annualized)
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
            metrics["sharpe_ratio"] = round(float(sharpe), 2)
        else:
            metrics["sharpe_ratio"] = 0.0

        metrics["final_equity"] = round(float(equity.iloc[-1]), 2)
        metrics["initial_equity"] = round(initial_equity, 2)

    else:
        metrics["max_drawdown_pct"] = 0.0
        metrics["max_intraday_drawdown_pct"] = 0.0
        metrics["best_day_pct"] = 0.0
        metrics["worst_day_pct"] = 0.0
        metrics["sharpe_ratio"] = 0.0
        metrics["final_equity"] = round(initial_equity + total_pnl, 2)
        metrics["initial_equity"] = round(initial_equity, 2)

    # -----------------------------------------------------------------------
    # Strategy breakdown
    # -----------------------------------------------------------------------
    if "strategy" in df.columns:
        strategy_pnl = df.groupby("strategy")["pnl"].sum().round(2).to_dict()
        metrics["strategy_breakdown"] = strategy_pnl

    return metrics
