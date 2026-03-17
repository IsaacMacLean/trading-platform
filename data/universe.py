"""
Universe — base list of ~200 liquid US stocks + ETFs.
"""
from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# Base universe: S&P 500 majors, sector ETFs, popular momentum names
# ---------------------------------------------------------------------------

BASE_UNIVERSE: List[str] = [
    # Broad market ETFs
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO",

    # Sector ETFs
    "XLF", "XLK", "XLE", "XLV", "XLI", "XLU", "XLP", "XLRE", "XLC", "XLB",
    "GLD", "SLV", "USO", "TLT", "HYG",

    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA",
    "AVGO", "ORCL", "CRM", "ADBE", "INTC", "AMD", "QCOM", "TXN",
    "MU", "AMAT", "LRCX", "KLAC", "MRVL", "PANW", "CRWD", "FTNT",
    "SNOW", "PLTR", "NET", "DDOG", "ZS", "OKTA", "MDB", "CFLT",

    # Financial
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "COF",
    "USB", "PNC", "TFC", "FITB", "KEY", "RF",

    # Healthcare / Biotech
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "BMY", "GILD", "AMGN",
    "BIIB", "REGN", "VRTX", "MRNA", "BNTX", "ILMN", "ISRG",

    # Consumer
    "AMZN", "COST", "WMT", "TGT", "HD", "LOW", "NKE", "SBUX", "MCD",
    "YUM", "CMG", "DKNG", "WYNN", "MGM", "LVS",

    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB", "HAL", "DVN", "OXY", "MPC", "VLO",

    # Industrial / Defense
    "BA", "LMT", "RTX", "NOC", "GD", "GE", "CAT", "DE", "HON", "MMM",
    "UPS", "FDX", "CSX", "NSC",

    # Autos / EV
    "TSLA", "GM", "F", "RIVN", "LCID",

    # Comms / Media
    "T", "VZ", "NFLX", "DIS", "CMCSA", "PARA", "WBD",

    # Real estate
    "AMT", "PLD", "CCI", "EQIX", "PSA", "O",

    # Momentum / meme adjacent
    "GME", "AMC", "BBBY", "SOFI", "HOOD", "COIN", "MSTR", "RIOT", "MARA",
    "UPST", "AFRM", "OPEN", "CLOV", "SPCE",

    # Semiconductors extra
    "SMCI", "ARM", "WOLF", "ON", "SWKS", "MPWR",

    # Biotech high-vol
    "SAVA", "ACAD", "SAGE", "NKTR", "ARWR", "AGEN",

    # ETF leveraged (high vol)
    "TQQQ", "SQQQ", "SPXL", "SPXS", "SOXL", "SOXS", "LABU", "LABD",
    "TNA", "TZA", "FAS", "FAZ", "UVXY", "VXX",

    # Misc high-volume
    "SQ", "PYPL", "V", "MA", "UBER", "LYFT", "ABNB", "DASH", "RBLX",
    "SNAP", "PINS", "TWTR", "SHOP", "ETSY", "W",
    "ZM", "DOCU", "PTON", "BYND", "CHWY", "WISH",
    "NIO", "XPEV", "LI", "BIDU", "JD", "BABA",
]

# Deduplicate while preserving order
_seen = set()
_deduped = []
for _s in BASE_UNIVERSE:
    if _s not in _seen:
        _deduped.append(_s)
        _seen.add(_s)
BASE_UNIVERSE = _deduped


def get_tradeable_universe(
    min_price: float = 5.0,
    max_price: float = 500.0,
    fetcher=None,
) -> List[str]:
    """
    Return BASE_UNIVERSE filtered to basic tradeable criteria.
    If fetcher is None, returns the full base universe without price filtering.
    With a fetcher, filter out symbols outside price range.
    """
    if fetcher is None:
        return list(BASE_UNIVERSE)

    tradeable = []
    snapshot = {}
    try:
        snapshot = fetcher.get_premarket_snapshot(BASE_UNIVERSE)
    except Exception:
        return list(BASE_UNIVERSE)

    for symbol in BASE_UNIVERSE:
        data = snapshot.get(symbol)
        if data is None:
            tradeable.append(symbol)  # include if no data
            continue
        price = data.get("close", 0)
        if min_price <= price <= max_price:
            tradeable.append(symbol)

    return tradeable
