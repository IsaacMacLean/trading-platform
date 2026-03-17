"""
Base strategy and Signal dataclass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Signal:
    symbol: str
    strategy: str
    direction: str          # "long" or "short"
    entry_price: float
    stop_price: float
    target_price: float
    conviction: int = 1
    qty: int = 0
    notes: str = ""


class BaseStrategy:
    """Abstract base strategy. Subclasses implement generate_signals()."""

    name: str = "base"

    def generate_signals(
        self,
        watchlist: list,
        fetcher,
        indicators,
    ) -> List[Signal]:
        """
        Given a watchlist of dicts (from Scanner), fetcher, and indicators module,
        return a list of Signal objects.
        """
        raise NotImplementedError
