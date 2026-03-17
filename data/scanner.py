"""
Scanner — pre-market gapper detection and intraday momentum scanning.
"""
from __future__ import annotations

from typing import Dict, List
from datetime import datetime, timedelta

import pytz
from loguru import logger

from data.fetcher import AlpacaFetcher
from config import (
    SCANNER_MIN_GAP_PCT,
    SCANNER_MIN_RVOL,
    SCANNER_MIN_PRICE,
    SCANNER_MAX_PRICE,
    SCANNER_MIN_AVG_VOLUME,
)

ET = pytz.timezone("America/New_York")


class Scanner:
    """Scans a universe for high-probability trade setups."""

    def __init__(self, fetcher: AlpacaFetcher | None = None):
        self.fetcher = fetcher or AlpacaFetcher()
        self._todays_gappers: List[dict] = []

    # ------------------------------------------------------------------
    # Pre-market scan
    # ------------------------------------------------------------------

    def scan_premarket(self, universe: List[str]) -> List[dict]:
        """
        Identify stocks gapping >SCANNER_MIN_GAP_PCT with elevated pre-market volume.
        Returns list of dicts: {symbol, gap_pct, rvol, price, prev_close}.
        """
        logger.info(f"Pre-market scan: {len(universe)} symbols")
        snapshot = self.fetcher.get_premarket_snapshot(universe)
        gappers = []

        for symbol, data in snapshot.items():
            try:
                price = data.get("close", 0)
                prev_close = data.get("prev_close", 0)
                gap_pct = data.get("gap_pct", 0)
                volume = data.get("volume", 0)

                if price < SCANNER_MIN_PRICE or price > SCANNER_MAX_PRICE:
                    continue

                if abs(gap_pct) < SCANNER_MIN_GAP_PCT:
                    continue

                # Check average daily volume
                daily = self.fetcher.get_daily_bars(symbol, days=20)
                if daily.empty:
                    continue
                avg_vol = float(daily["volume"].tail(10).mean())
                if avg_vol < SCANNER_MIN_AVG_VOLUME:
                    continue

                # Rough RVOL estimate for premarket
                rvol = volume / (avg_vol / 6.5 / 60) if avg_vol > 0 else 1.0

                gappers.append({
                    "symbol": symbol,
                    "gap_pct": round(gap_pct, 2),
                    "rvol": round(rvol, 2),
                    "price": round(price, 2),
                    "prev_close": round(prev_close, 2),
                    "volume": int(volume),
                    "avg_daily_volume": int(avg_vol),
                    "direction": "up" if gap_pct > 0 else "down",
                })
            except Exception as exc:
                logger.warning(f"Premarket scan {symbol}: {exc}")

        # Sort by absolute gap_pct descending
        gappers.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)
        self._todays_gappers = gappers[:20]
        logger.info(f"Pre-market scan found {len(self._todays_gappers)} gappers")
        return self._todays_gappers

    # ------------------------------------------------------------------
    # Intraday scan
    # ------------------------------------------------------------------

    def scan_intraday(self, universe: List[str]) -> List[dict]:
        """
        Stocks up/down >2% in last 30 min with RVOL>3. Runs every 5 min.
        Returns list of dicts: {symbol, pct_change_30m, rvol, price, direction}.
        """
        logger.info(f"Intraday scan: {len(universe)} symbols")
        movers = []

        for symbol in universe:
            try:
                df = self.fetcher.get_minute_bars(symbol, days=2)
                if df.empty or len(df) < 30:
                    continue

                # Convert to ET
                import pandas as pd
                df_et = df.copy()
                df_et.index = df_et.index.tz_convert(ET)

                # Today's bars only
                today = datetime.now(ET).date()
                today_df = df_et[df_et.index.date == today]
                if len(today_df) < 5:
                    continue

                current_price = float(today_df["close"].iloc[-1])
                price_30min_ago = float(today_df["close"].iloc[max(0, len(today_df) - 31)])
                pct_change = (current_price - price_30min_ago) / price_30min_ago * 100

                if abs(pct_change) < 2.0:
                    continue

                # Relative volume
                rvol = self.fetcher.get_rvol(symbol)
                if rvol < SCANNER_MIN_RVOL:
                    continue

                if current_price < SCANNER_MIN_PRICE or current_price > SCANNER_MAX_PRICE:
                    continue

                movers.append({
                    "symbol": symbol,
                    "pct_change_30m": round(pct_change, 2),
                    "rvol": round(rvol, 2),
                    "price": round(current_price, 2),
                    "direction": "up" if pct_change > 0 else "down",
                    "scan_time": datetime.now(ET).isoformat(),
                })
            except Exception as exc:
                logger.warning(f"Intraday scan {symbol}: {exc}")

        movers.sort(key=lambda x: abs(x["pct_change_30m"]), reverse=True)
        logger.info(f"Intraday scan found {len(movers)} movers")
        return movers[:10]

    # ------------------------------------------------------------------
    # Combined watchlist
    # ------------------------------------------------------------------

    def get_todays_watchlist(self, universe: List[str]) -> List[dict]:
        """
        Combines pre-market and intraday results.
        Returns top 20 candidates with deduplication.
        """
        premarket = self.scan_premarket(universe)
        intraday = self.scan_intraday(universe)

        seen: Dict[str, dict] = {}
        for item in premarket:
            seen[item["symbol"]] = dict(item, source="premarket")

        for item in intraday:
            sym = item["symbol"]
            if sym in seen:
                # merge: keep higher rvol
                if item["rvol"] > seen[sym].get("rvol", 0):
                    seen[sym].update(item)
                seen[sym]["source"] = "both"
            else:
                seen[sym] = dict(item, source="intraday")

        watchlist = sorted(seen.values(), key=lambda x: (
            x.get("rvol", 0) + abs(x.get("gap_pct", 0)) + abs(x.get("pct_change_30m", 0))
        ), reverse=True)

        return watchlist[:20]
