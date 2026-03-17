"""
FastAPI dashboard application.
Serves the war-room trading dashboard with live data via WebSocket.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List

import pytz
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from loguru import logger

import config

ET = pytz.timezone("America/New_York")

app = FastAPI(title="Trading Platform Dashboard", version="1.0.0")

# Static files and templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Global monitor reference — set by main.py at startup
_monitor = None


def set_monitor(monitor) -> None:
    """Register the Monitor instance with the dashboard."""
    global _monitor
    _monitor = monitor


def _get_state() -> dict:
    """Get current state from monitor or return defaults."""
    if _monitor is not None:
        return _monitor.get_state()
    return {
        "positions": [],
        "account": {
            "equity": 100000.0,
            "cash": 100000.0,
            "buying_power": 200000.0,
            "day_pnl": 0.0,
            "day_pnl_pct": 0.0,
        },
        "equity_curve": [],
        "scanner_feed": [],
        "trade_log": [],
        "risk": {
            "current_drawdown_pct": 0.0,
            "total_exposure_pct": 0.0,
            "num_positions": 0,
            "daily_loss_limit_pct": config.DAILY_LOSS_LIMIT * 100,
            "circuit_breaker_pct": config.CIRCUIT_BREAKER_PCT * 100,
            "distance_to_daily_limit": config.DAILY_LOSS_LIMIT * 100,
        },
        "status": "IDLE",
        "last_update": datetime.now(ET).isoformat(),
    }


# ------------------------------------------------------------------
# HTTP routes
# ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/account")
async def get_account():
    """Account vitals: equity, P&L, cash, buying power."""
    state = _get_state()
    return state.get("account", {})


@app.get("/api/positions")
async def get_positions():
    """Open positions with live P&L."""
    state = _get_state()
    return state.get("positions", [])


@app.get("/api/equity-curve")
async def get_equity_curve():
    """Today's minute-level equity data."""
    state = _get_state()
    return state.get("equity_curve", [])


@app.get("/api/scanner-feed")
async def get_scanner_feed():
    """Latest scanner results."""
    state = _get_state()
    return state.get("scanner_feed", [])


@app.get("/api/trade-log")
async def get_trade_log():
    """Today's completed trades."""
    state = _get_state()
    return state.get("trade_log", [])


@app.get("/api/risk")
async def get_risk():
    """Risk metrics: drawdown, win/loss, distances to limits."""
    state = _get_state()
    return state.get("risk", {})


@app.get("/api/status")
async def get_status():
    """System status."""
    state = _get_state()
    return {
        "status": state.get("status", "IDLE"),
        "last_update": state.get("last_update"),
    }


# ------------------------------------------------------------------
# WebSocket
# ------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket connected: {ws.client}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Push update every 10 seconds
            state = _get_state()
            await websocket.send_json({
                "type": "state_update",
                "data": state,
                "timestamp": datetime.now(ET).isoformat(),
            })
            await asyncio.sleep(config.REFRESH_INTERVAL_SEC)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected: {websocket.client}")
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
        manager.disconnect(websocket)


@app.on_event("startup")
async def startup():
    logger.info(f"Dashboard starting on port {config.DASHBOARD_PORT}")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Dashboard shutting down")
