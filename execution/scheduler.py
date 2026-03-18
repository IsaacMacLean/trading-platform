"""
Scheduler — APScheduler-based job manager for the trading day.
All times are Eastern Time. Respects Alpaca market calendar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from alpaca.trading.client import TradingClient
import config

ET = pytz.timezone("America/New_York")


class Scheduler:
    """
    Manages all time-based trading jobs.
    Jobs fire at configured times (Eastern Time).
    """

    def __init__(self):
        self.trading_client = TradingClient(
            config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True
        )
        self.scheduler = BackgroundScheduler(timezone=ET)
        self._callbacks: dict = {}

    # ------------------------------------------------------------------
    # Market calendar check
    # ------------------------------------------------------------------

    def is_market_day(self) -> bool:
        """Return True if today is a trading day per Alpaca calendar."""
        try:
            clock = self.trading_client.get_clock()
            return not clock.is_open  # open OR next_open is today
        except Exception:
            return True  # assume open if we can't check

    def is_market_open(self) -> bool:
        """Return True if market is currently open."""
        try:
            return self.trading_client.get_clock().is_open
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Job registration
    # ------------------------------------------------------------------

    def register(self, name: str, callback: Callable) -> None:
        """Register a named callback."""
        self._callbacks[name] = callback

    def _safe_call(self, name: str) -> None:
        """Call a registered callback with error handling."""
        fn = self._callbacks.get(name)
        if fn is None:
            logger.warning(f"Scheduler: no callback registered for '{name}'")
            return
        try:
            logger.info(f"[SCHEDULER] → {name}")
            fn()
        except Exception as exc:
            logger.error(f"Scheduler job '{name}' failed: {exc}")

    # ------------------------------------------------------------------
    # Setup all trading day jobs
    # ------------------------------------------------------------------

    def setup_jobs(self) -> None:
        """
        Configure all scheduled jobs per CLAUDE.md spec.
        Schedule (ET):
          07:00 — premarket_scan
          09:25 — final_scan
          09:35 — opening_range_calc
          09:45 — first_trades (ORB + gap fade)
          09:45–15:30 every 1 min — intraday_scan
          15:30 — overnight_scan
          15:45 — overnight_entries
          15:55 — close_intraday
          16:00 — eod_report
        """
        scheduler = self.scheduler

        # 7:00 AM — pre-market scan
        scheduler.add_job(
            lambda: self._safe_call("premarket_scan"),
            CronTrigger(hour=7, minute=0, timezone=ET),
            id="premarket_scan",
            replace_existing=True,
        )

        # 9:25 AM — final pre-market scan
        scheduler.add_job(
            lambda: self._safe_call("final_scan"),
            CronTrigger(hour=9, minute=25, timezone=ET),
            id="final_scan",
            replace_existing=True,
        )

        # 9:35 AM — calculate opening range levels
        scheduler.add_job(
            lambda: self._safe_call("opening_range_calc"),
            CronTrigger(hour=9, minute=35, timezone=ET),
            id="opening_range_calc",
            replace_existing=True,
        )

        # 9:45 AM — close overnight positions (next morning exit) + fire first trades
        scheduler.add_job(
            lambda: self._safe_call("close_overnight"),
            CronTrigger(hour=9, minute=45, timezone=ET),
            id="close_overnight",
            replace_existing=True,
        )

        # 9:45 AM — fire first trades (ORB + gap fade)
        scheduler.add_job(
            lambda: self._safe_call("first_trades"),
            CronTrigger(hour=9, minute=45, timezone=ET),
            id="first_trades",
            replace_existing=True,
        )

        # Every 1 minute 9:45 AM – 3:30 PM — intraday scan
        scheduler.add_job(
            lambda: self._safe_call("intraday_scan"),
            CronTrigger(
                minute="*",
                hour="9-15",
                day_of_week="mon-fri",
                timezone=ET,
            ),
            id="intraday_scan",
            replace_existing=True,
        )

        # 3:30 PM — overnight swing scan
        scheduler.add_job(
            lambda: self._safe_call("overnight_scan"),
            CronTrigger(hour=15, minute=30, timezone=ET),
            id="overnight_scan",
            replace_existing=True,
        )

        # 3:45 PM — enter overnight positions
        scheduler.add_job(
            lambda: self._safe_call("overnight_entries"),
            CronTrigger(hour=15, minute=45, timezone=ET),
            id="overnight_entries",
            replace_existing=True,
        )

        # 3:55 PM — close all intraday positions
        scheduler.add_job(
            lambda: self._safe_call("close_intraday"),
            CronTrigger(hour=15, minute=55, timezone=ET),
            id="close_intraday",
            replace_existing=True,
        )

        # 4:00 PM — EOD report
        scheduler.add_job(
            lambda: self._safe_call("eod_report"),
            CronTrigger(hour=16, minute=0, timezone=ET),
            id="eod_report",
            replace_existing=True,
        )

        logger.info("Scheduler jobs configured.")

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        self.setup_jobs()
        self.scheduler.start()
        logger.info("Scheduler started.")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")

    def list_jobs(self) -> None:
        """Print all scheduled jobs."""
        for job in self.scheduler.get_jobs():
            logger.info(f"  Job: {job.id} | Next: {job.next_run_time}")
