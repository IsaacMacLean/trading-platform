"""
run_dashboard.py — Launch the FastAPI war-room dashboard.

Usage:
    python run_dashboard.py
    python run_dashboard.py --port 8050 --host 0.0.0.0
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

import uvicorn
from loguru import logger

import config
from execution.monitor import Monitor
from dashboard.app import app, set_monitor

# Configure loguru
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level="INFO",
    colorize=True,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Launch trading dashboard")
    parser.add_argument("--port", type=int, default=config.DASHBOARD_PORT,
                        help=f"Port to listen on (default: {config.DASHBOARD_PORT})")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--no-monitor", action="store_true",
                        help="Skip starting the position monitor thread")
    return parser.parse_args()


def main():
    args = parse_args()

    logger.info("=" * 55)
    logger.info("     TRADING PLATFORM DASHBOARD")
    logger.info("=" * 55)

    # Start monitor
    monitor = None
    if not args.no_monitor:
        try:
            monitor = Monitor()
            monitor.start()
            set_monitor(monitor)
            logger.info("Monitor started — fetching live data from Alpaca")
        except Exception as exc:
            logger.warning(f"Monitor failed to start (running in demo mode): {exc}")

    logger.info(f"Dashboard URL: http://{args.host}:{args.port}")
    logger.info("Press Ctrl+C to stop")

    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="warning",
            reload=False,
        )
    except KeyboardInterrupt:
        logger.info("Dashboard stopped.")
    finally:
        if monitor:
            monitor.stop()


if __name__ == "__main__":
    main()
