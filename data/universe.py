"""
Universe — base list of ~200 liquid US stocks + ETFs.
"""
from __future__ import annotations

from typing import Dict, List

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

    # Momentum / meme adjacent (removed delisted/dead: BBBY, OPEN, CLOV, SPCE)
    "GME", "AMC", "SOFI", "HOOD", "COIN", "MSTR", "RIOT", "MARA",
    "UPST", "AFRM",

    # Semiconductors extra
    "SMCI", "ARM", "WOLF", "ON", "SWKS", "MPWR",

    # Biotech high-vol
    "SAVA", "ACAD", "SAGE", "NKTR", "ARWR", "AGEN",

    # ETF leveraged (high vol)
    "TQQQ", "SQQQ", "SPXL", "SPXS", "SOXL", "SOXS", "LABU", "LABD",
    "TNA", "TZA", "FAS", "FAZ", "UVXY", "VXX",

    # Misc high-volume
    # Removed delisted/dead: TWTR, BYND, WISH, PTON (mostly dead volume)
    "SQ", "PYPL", "V", "MA", "UBER", "LYFT", "ABNB", "DASH", "RBLX",
    "SNAP", "PINS", "SHOP", "ETSY", "W",
    "ZM", "DOCU", "CHWY",
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


# ---------------------------------------------------------------------------
# Sector ETF map — used by aggressor to confirm sector is aligned before entry
# ---------------------------------------------------------------------------

SECTOR_ETF: Dict[str, str] = {
    # Technology
    "AAPL":"XLK","MSFT":"XLK","NVDA":"XLK","AMD":"XLK","INTC":"XLK",
    "AVGO":"XLK","QCOM":"XLK","TXN":"XLK","CRM":"XLK","ADBE":"XLK",
    "ORCL":"XLK","MU":"XLK","AMAT":"XLK","LRCX":"XLK","KLAC":"XLK",
    "MRVL":"XLK","PANW":"XLK","CRWD":"XLK","FTNT":"XLK","SNOW":"XLK",
    "PLTR":"XLK","NET":"XLK","DDOG":"XLK","ZS":"XLK","OKTA":"XLK",
    "SMCI":"XLK","ARM":"XLK","SQ":"XLK","PYPL":"XLK","SHOP":"XLK",
    # Financial
    "JPM":"XLF","BAC":"XLF","WFC":"XLF","GS":"XLF","MS":"XLF",
    "C":"XLF","BLK":"XLF","SCHW":"XLF","AXP":"XLF","COF":"XLF",
    "USB":"XLF","PNC":"XLF","V":"XLF","MA":"XLF","COIN":"XLF",
    # Healthcare
    "JNJ":"XLV","UNH":"XLV","PFE":"XLV","ABBV":"XLV","MRK":"XLV",
    "LLY":"XLV","BMY":"XLV","GILD":"XLV","AMGN":"XLV","BIIB":"XLV",
    "REGN":"XLV","VRTX":"XLV","MRNA":"XLV","ISRG":"XLV","ILMN":"XLV",
    # Energy
    "XOM":"XLE","CVX":"XLE","COP":"XLE","EOG":"XLE","SLB":"XLE",
    "HAL":"XLE","DVN":"XLE","OXY":"XLE","MPC":"XLE","VLO":"XLE",
    # Consumer Discretionary
    "AMZN":"XLY","TSLA":"XLY","HD":"XLY","NKE":"XLY","MCD":"XLY",
    "SBUX":"XLY","CMG":"XLY","TGT":"XLY","LOW":"XLY","DKNG":"XLY",
    "WYNN":"XLY","MGM":"XLY","LVS":"XLY","UBER":"XLY","ABNB":"XLY",
    # Consumer Staples
    "WMT":"XLP","COST":"XLP",
    # Industrials
    "BA":"XLI","GE":"XLI","HON":"XLI","CAT":"XLI","DE":"XLI",
    "UPS":"XLI","FDX":"XLI","LMT":"XLI","RTX":"XLI","NOC":"XLI","GD":"XLI",
    # Communication
    "GOOGL":"XLC","GOOG":"XLC","META":"XLC","NFLX":"XLC",
    "DIS":"XLC","CMCSA":"XLC","T":"XLC","VZ":"XLC","SNAP":"XLC",
    # Crypto / speculative — use QQQ as proxy
    "MSTR":"QQQ","RIOT":"QQQ","MARA":"QQQ","HOOD":"QQQ","SOFI":"QQQ",
    "UPST":"QQQ","AFRM":"QQQ","RBLX":"QQQ","DASH":"QQQ",
}


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
