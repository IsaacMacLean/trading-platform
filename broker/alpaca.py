import pandas as pd
import pytz
from datetime import datetime, timedelta
from loguru import logger

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY


class AlpacaBroker:
    def __init__(self):
        self.trading = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        self.data = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

    def get_account(self):
        return self.trading.get_account()

    def get_equity(self) -> float:
        return float(self.trading.get_account().equity)

    def get_positions(self) -> dict:
        return {p.symbol: p for p in self.trading.get_all_positions()}

    def is_market_open(self) -> bool:
        return self.trading.get_clock().is_open

    def get_bars(self, symbol: str, days: int = 60) -> pd.DataFrame:
        end = datetime.now(pytz.UTC)
        start = end - timedelta(days=days)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
        )
        bars = self.data.get_stock_bars(request)
        df = bars.df
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    def place_market_order(self, symbol: str, qty: int, side: str):
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        result = self.trading.submit_order(order_data=order)
        logger.info(f"Order submitted: {side.upper()} {qty} {symbol}")
        return result

    def close_position(self, symbol: str):
        try:
            self.trading.close_position(symbol)
            logger.info(f"Position closed: {symbol}")
        except Exception as e:
            logger.error(f"Failed to close {symbol}: {e}")
