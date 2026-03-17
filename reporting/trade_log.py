"""
TradeLogger — SQLite-backed trade logging.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pytz
from loguru import logger

ET = pytz.timezone("America/New_York")
DB_PATH = Path(__file__).parent.parent / "trades.db"


class TradeLogger:
    """
    Logs all trades to SQLite.
    Schema matches CLAUDE.md spec fields.
    """

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Create database and tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_open      TEXT,
                timestamp_close     TEXT,
                symbol              TEXT NOT NULL,
                direction           TEXT NOT NULL,
                strategy            TEXT,
                shares              INTEGER,
                entry_price         REAL,
                exit_price          REAL,
                pnl_dollars         REAL,
                pnl_percent         REAL,
                hold_time_minutes   REAL,
                exit_reason         TEXT,
                order_id            TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON trades(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_open   ON trades(timestamp_open)")
        conn.commit()
        conn.close()

    def log_trade(self, trade_dict: Dict) -> int:
        """
        Insert a trade record. Returns the new row ID.

        Expected keys (all optional except symbol/direction):
          timestamp_open, timestamp_close, symbol, direction, strategy,
          shares, entry_price, exit_price, pnl_dollars, pnl_percent,
          hold_time_minutes, exit_reason, order_id
        """
        now_str = datetime.now(ET).isoformat()
        row = (
            trade_dict.get("timestamp_open", now_str),
            trade_dict.get("timestamp_close", now_str),
            trade_dict.get("symbol", ""),
            trade_dict.get("direction", "long"),
            trade_dict.get("strategy", ""),
            trade_dict.get("shares", trade_dict.get("qty", 0)),
            trade_dict.get("entry_price", 0.0),
            trade_dict.get("exit_price", 0.0),
            trade_dict.get("pnl_dollars", trade_dict.get("pnl", 0.0)),
            trade_dict.get("pnl_percent", trade_dict.get("pnl_pct", 0.0)),
            trade_dict.get("hold_time_minutes", trade_dict.get("hold_minutes", 0.0)),
            trade_dict.get("exit_reason", ""),
            trade_dict.get("order_id", ""),
        )
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute(
                """INSERT INTO trades
                   (timestamp_open, timestamp_close, symbol, direction, strategy,
                    shares, entry_price, exit_price, pnl_dollars, pnl_percent,
                    hold_time_minutes, exit_reason, order_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                row,
            )
            conn.commit()
            row_id = cur.lastrowid
            conn.close()
            logger.debug(f"Trade logged: {trade_dict.get('symbol')} id={row_id}")
            return row_id
        except Exception as exc:
            logger.error(f"log_trade: {exc}")
            return -1

    def get_today_trades(self) -> List[Dict]:
        """Return all trades opened today (ET)."""
        today = datetime.now(ET).date().isoformat()
        return self._query(
            "SELECT * FROM trades WHERE timestamp_open LIKE ? ORDER BY id DESC",
            (today + "%",),
        )

    def get_all_trades(self) -> List[Dict]:
        """Return all trades, most recent first."""
        return self._query("SELECT * FROM trades ORDER BY id DESC")

    def get_trades_by_symbol(self, symbol: str) -> List[Dict]:
        """Return all trades for a specific symbol."""
        return self._query(
            "SELECT * FROM trades WHERE symbol=? ORDER BY id DESC",
            (symbol,),
        )

    def update_exit(
        self,
        trade_id: int,
        exit_price: float,
        pnl_dollars: float,
        pnl_percent: float,
        exit_reason: str,
        hold_time_minutes: float,
    ) -> None:
        """Update an existing trade record with exit information."""
        try:
            now_str = datetime.now(ET).isoformat()
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """UPDATE trades
                   SET timestamp_close=?, exit_price=?, pnl_dollars=?,
                       pnl_percent=?, exit_reason=?, hold_time_minutes=?
                   WHERE id=?""",
                (now_str, exit_price, pnl_dollars, pnl_percent, exit_reason, hold_time_minutes, trade_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"update_exit id={trade_id}: {exc}")

    def _query(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Execute a query and return list of dicts."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"_query: {exc}")
            return []
