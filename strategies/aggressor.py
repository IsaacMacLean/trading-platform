"""
Aggressor Meta-Strategy — primary production strategy.
Collects signals from all 6 sub-strategies, scores conviction, returns top picks.
"""
from __future__ import annotations

from collections import defaultdict
from typing import List, Dict

from loguru import logger

from strategies.base import BaseStrategy, Signal
from strategies.gap_fade import GapFade
from strategies.opening_range import OpeningRangeBreakout
from strategies.momentum_surge import MomentumSurge
from strategies.vwap_bounce import VWAPBounce
from strategies.overnight_swing import OvernightSwing
from strategies.news_momentum import NewsAndVolumeMomentum

import config

TOP_N = 5
MIN_CONVICTION = 1


class Aggressor(BaseStrategy):
    """
    Meta-strategy: runs all sub-strategies and picks highest-conviction signals.

    Conviction scoring:
      +2 if multiple strategies agree on same stock + direction
      +1 for RVOL > 5
      +1 for strong trend alignment (above all MAs for longs)
      +1 if stock is a top-3 gapper of the day
    """

    name = "aggressor"

    def __init__(self):
        self.sub_strategies: List[BaseStrategy] = [
            GapFade(),
            OpeningRangeBreakout(),
            MomentumSurge(),
            VWAPBounce(),
            OvernightSwing(),
            NewsAndVolumeMomentum(),
        ]
        self._top_gappers: List[str] = []

    def set_top_gappers(self, gappers: List[dict]) -> None:
        """Call before generate_signals with today's pre-market gappers."""
        self._top_gappers = [g["symbol"] for g in gappers[:3]]

    def generate_signals(self, watchlist: list, fetcher, indicators) -> List[Signal]:
        """
        Run all sub-strategies, aggregate and score signals, return top picks.
        """
        # Collect raw signals from each sub-strategy
        raw: Dict[str, List[Signal]] = defaultdict(list)

        for strat in self.sub_strategies:
            try:
                sigs = strat.generate_signals(watchlist, fetcher, indicators)
                for sig in sigs:
                    raw[sig.symbol].append(sig)
                    logger.debug(
                        f"  [{strat.name}] {sig.symbol} {sig.direction} "
                        f"entry={sig.entry_price:.2f} conv={sig.conviction}"
                    )
            except Exception as exc:
                logger.warning(f"Aggressor sub-strategy {strat.name}: {exc}")

        # Build watchlist RVOL lookup
        rvol_map = {item.get("symbol", ""): item.get("rvol", 1.0) for item in watchlist}

        # Score each symbol
        scored: List[Signal] = []

        for symbol, sigs in raw.items():
            if not sigs:
                continue

            # Direction agreement
            long_count = sum(1 for s in sigs if s.direction == "long")
            short_count = sum(1 for s in sigs if s.direction == "short")
            direction = "long" if long_count >= short_count else "short"

            # Use highest-conviction signal for entry/stop/target
            best = max(sigs, key=lambda s: s.conviction)

            # Base conviction from sub-strategies
            total_conviction = best.conviction

            # +2 multi-strategy agreement
            if len(sigs) >= 2:
                total_conviction += 2

            # +1 RVOL > 5
            rvol = rvol_map.get(symbol, 1.0)
            if rvol > 5:
                total_conviction += 1

            # +1 strong trend alignment (use best's notes as proxy)
            if direction == "long" and "above" in best.notes.lower():
                total_conviction += 1

            # +1 top-3 gapper
            if symbol in self._top_gappers:
                total_conviction += 1

            scored.append(Signal(
                symbol=symbol,
                strategy=self.name,
                direction=direction,
                entry_price=best.entry_price,
                stop_price=best.stop_price,
                target_price=best.target_price,
                conviction=total_conviction,
                notes=(
                    f"strategies={[s.strategy for s in sigs]} "
                    f"rvol={rvol:.1f} "
                    f"gapper={'yes' if symbol in self._top_gappers else 'no'}"
                ),
            ))

        # Sort by conviction descending
        scored.sort(key=lambda s: s.conviction, reverse=True)
        top = scored[:TOP_N]

        if top:
            logger.info(
                f"Aggressor top signals: "
                + ", ".join(f"{s.symbol}({s.direction},conv={s.conviction})" for s in top)
            )

        return top

    def apply_position_sizing(
        self,
        signals: List[Signal],
        equity: float,
    ) -> List[Signal]:
        """
        Apply 15-25% position sizing to top Aggressor signals.
        Higher conviction gets larger size.
        """
        if not signals:
            return signals

        max_conv = max(s.conviction for s in signals)
        result = []
        for sig in signals:
            if max_conv > 0:
                size_pct = 0.15 + (sig.conviction / max_conv) * 0.10  # 15-25%
            else:
                size_pct = config.MAX_POSITION_PCT

            size_pct = min(size_pct, config.MAX_POSITION_PCT)
            allocation = equity * size_pct
            qty = max(1, int(allocation / sig.entry_price)) if sig.entry_price > 0 else 1
            sig.qty = qty
            result.append(sig)

        return result
