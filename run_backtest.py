"""
run_backtest.py — Run BacktestEngine on last 30 days, print metrics, save HTML report.

Usage:
    python run_backtest.py
    python run_backtest.py --days 60 --symbols AAPL NVDA TSLA
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

import config
from backtesting.engine import BacktestEngine
from backtesting.metrics import compute_metrics
from backtesting.results import print_results, save_html_report
from data.universe import BASE_UNIVERSE

# Configure loguru for clean output
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level="INFO",
    colorize=True,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Run backtest on trading strategies")
    parser.add_argument("--days", type=int, default=config.BACKTEST_DAYS,
                        help=f"Number of days to backtest (default: {config.BACKTEST_DAYS})")
    parser.add_argument("--equity", type=float, default=100_000.0,
                        help="Starting equity (default: 100000)")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Symbols to test (default: top 20 from BASE_UNIVERSE)")
    parser.add_argument("--output", type=str, default="backtest_report.html",
                        help="Output HTML report path")
    return parser.parse_args()


def main():
    args = parse_args()

    # Select symbols
    if args.symbols:
        symbols = args.symbols
    else:
        # Use a focused subset of high-volume names
        symbols = [
            "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
            "META", "GOOGL", "AMD", "MSTR", "COIN",
            "TQQQ", "SQQQ", "SOFI", "PLTR", "RIVN", "NIO",
        ]

    logger.info(f"Starting backtest: {args.days} days | {len(symbols)} symbols | equity=${args.equity:,.0f}")
    logger.info(f"Symbols: {symbols}")

    # Run engine
    engine = BacktestEngine(
        symbols=symbols,
        days=args.days,
        initial_equity=args.equity,
    )

    try:
        results = engine.run()
    except Exception as exc:
        logger.error(f"Backtest failed: {exc}")
        sys.exit(1)

    trades_df = results.get("trades")
    equity_curve = results.get("equity_curve")
    initial_equity = results.get("initial_equity", args.equity)

    if trades_df is None or trades_df.empty:
        logger.warning("No trades generated in backtest period.")
        print("\n  No trades found. Try a longer backtest window or check data availability.\n")
        return

    # Compute metrics
    metrics = compute_metrics(
        trades_df=trades_df,
        equity_curve=equity_curve,
        initial_equity=initial_equity,
    )

    # Print to console
    print_results(metrics)

    # Save HTML report
    output_path = args.output
    save_html_report(metrics, trades_df, path=output_path)
    logger.info(f"Report saved: {output_path}")
    print(f"\n  Full report: {Path(output_path).resolve()}\n")


if __name__ == "__main__":
    main()
