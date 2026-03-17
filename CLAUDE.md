# Aggressive Short-Term Trading Platform — CLAUDE.md

## Project Overview

Build an **aggressive short-term quantitative trading platform** for US equities using the **Alpaca Paper Trading API**. The system targets **maximum returns over 1–3 day holding periods** using high-conviction intraday and overnight swing strategies with concentrated positions and leveraged exposure.

**Goal:** Maximize absolute returns over very short timeframes. Accept high volatility and drawdown risk in exchange for upside potential. This is a paper trading system for experimentation.

**Time Horizon:** Intraday to 3-day swings. No position held longer than 3 trading days.

---

## Architecture

```
trading-platform/
├── CLAUDE.md
├── .env                       # API keys (NEVER commit)
├── .env.example
├── .gitignore
├── requirements.txt
├── config.py                  # Central config — aggressive settings
│
├── data/
│   ├── fetcher.py             # Real-time + historical data (Alpaca + yfinance)
│   ├── indicators.py          # Technical indicators (fast, intraday-focused)
│   ├── scanner.py             # Pre-market scanner: gaps, volume, catalysts
│   └── universe.py            # Dynamic universe: today's movers, not a static list
│
├── strategies/
│   ├── base.py                # Abstract base strategy
│   ├── gap_fade.py            # Fade large overnight gaps
│   ├── opening_range.py       # Opening range breakout (first 15-30 min)
│   ├── momentum_surge.py      # Ride intraday momentum surges on high volume
│   ├── vwap_bounce.py         # VWAP mean-reversion scalps
│   ├── overnight_swing.py     # Hold high-momentum setups overnight for gap-up
│   ├── news_momentum.py       # Ride stocks with unusual volume (proxy for news)
│   └── aggressor.py           # Meta-strategy: picks highest-conviction signals, sizes up
│
├── backtesting/
│   ├── engine.py              # Intraday backtesting with minute bars
│   ├── metrics.py             # Short-term focused metrics
│   └── results.py             # Quick results display
│
├── risk/
│   ├── manager.py             # Aggressive but not suicidal risk management
│   ├── stop_loss.py           # Tight intraday stops
│   └── sizing.py              # Kelly criterion / volatility-based aggressive sizing
│
├── execution/
│   ├── trader.py              # Fast order execution via Alpaca
│   ├── scheduler.py           # Minute-by-minute during market hours
│   └── monitor.py             # Real-time P&L and fill tracking
│
├── dashboard/
│   ├── app.py                 # FastAPI real-time dashboard
│   ├── templates/
│   │   └── index.html         # Live trading dashboard
│   └── static/
│       ├── css/style.css
│       └── js/dashboard.js
│
├── reporting/
│   ├── performance.py         # End-of-day P&L report
│   ├── trade_log.py           # Every trade logged
│   └── alerts.py              # Real-time alerts
│
├── main.py                    # Entry point — scan, signal, trade, repeat
├── run_backtest.py            # Backtest aggressive strategies on recent data
└── run_dashboard.py           # Launch monitoring dashboard
```

---

## Environment Setup

### Dependencies (requirements.txt)
```
alpaca-trade-api>=3.0.0
yfinance>=0.2.0
pandas>=2.0.0
numpy>=1.24.0
scipy>=1.10.0
ta>=0.10.0
fastapi>=0.100.0
uvicorn>=0.23.0
jinja2>=3.1.0
websockets>=11.0
apscheduler>=3.10.0
python-dotenv>=1.0.0
plotly>=5.15.0
requests>=2.31.0
aiohttp>=3.9.0
```

### .env file
```
ALPACA_API_KEY=<from environment>
ALPACA_SECRET_KEY=<from environment>
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

**CRITICAL**: Never hardcode API keys. Always load from .env using python-dotenv.

---

## Core Philosophy: How to Make Big Money Fast (Theoretically)

Short-term alpha comes from:
1. **Volatility** — Trade the most volatile stocks each day. Boring stocks don't move enough.
2. **Concentration** — Spread across 3-5 positions max, not 50. Diversification kills short-term returns.
3. **Timing** — Most intraday opportunity is in the first hour and last 30 minutes. The midday is dead.
4. **Momentum** — In the short term, momentum is the strongest factor. Stocks that are moving tend to keep moving.
5. **Volume surges** — Unusual volume = something is happening. Get in early on the move.
6. **Overnight risk as opportunity** — Holding momentum stocks overnight captures gap-ups (but also gap-downs).

---

## Dynamic Universe: What to Trade Each Day

### `data/scanner.py`

This is the most important file. Every morning before market open, scan for:

**Pre-Market Gappers (run at 8:00 AM ET):**
- Stocks gapping up or down > 3% from previous close
- Pre-market volume > 2x normal
- Price between $5 and $200 (enough volatility, enough liquidity)
- Average daily volume > 1M shares (need liquidity for fast execution)

**Intraday Movers (run every 5 minutes during market hours):**
- Stocks up/down > 2% in last 30 minutes
- Current volume > 3x average volume for this time of day
- Relative volume (RVOL) > 3.0

**Selection:** Pick the top 10 candidates each scan, then strategies choose from this pool.

### `data/universe.py`
- Maintain a watchlist of ~200 liquid mid/large-cap stocks as a base universe
- Every day, the scanner narrows this to 10-20 "in play" stocks
- Additionally include any stock from the broader market that meets the gap/volume criteria
- Filter out stocks with earnings in the next 24 hours (unpredictable binary events — unless a strategy specifically targets post-earnings momentum)

---

## Strategy Specifications

### 1. Gap Fade (`strategies/gap_fade.py`)
**Idea:** Large overnight gaps tend to partially fill in the first 1-2 hours.
- Trigger: Stock gaps up > 5% on no significant news (just momentum/sympathy)
- Short (or avoid if short-selling restricted) stocks that gap up > 5%
- Go long stocks that gap down > 5% (oversold bounce)
- Enter at market open + 5 minutes (let opening chaos settle)
- Target: 50% of the gap filled
- Stop: Gap extends by another 2% against you
- Time stop: Close by 11:00 AM if target not hit
- **Position size: 15-20% of portfolio per trade**

### 2. Opening Range Breakout (`strategies/opening_range.py`)
**Idea:** The first 15-30 minutes establish the day's range. Breakouts from this range tend to continue.
- Calculate the high and low of the first 15 minutes after open (9:30-9:45 AM)
- Buy when price breaks above the opening range high with volume confirmation (volume > 1.5x average)
- Short when price breaks below the opening range low with volume confirmation
- Stop: Middle of the opening range (risking half the range width)
- Target: 2x the opening range width from breakout point
- Time stop: Close by 3:00 PM if target not hit
- Only trade stocks from the scanner (high RVOL, in-play names)
- **Position size: 15-20% of portfolio per trade**

### 3. Momentum Surge (`strategies/momentum_surge.py`)
**Idea:** When a stock starts running on huge volume, ride the wave.
- Detect: Price moves > 1.5% in 5 minutes on volume > 5x average
- Enter immediately in the direction of the move
- Use a fast trailing stop: 0.5% from the high (for longs)
- Let winners run, cut losers immediately
- Maximum hold: 2 hours
- Stack into winners: if a position is up > 2%, add another 25% to the position
- **Initial position size: 10% of portfolio, scale up to 20%**

### 4. VWAP Bounce (`strategies/vwap_bounce.py`)
**Idea:** Stocks in uptrends tend to bounce off VWAP. Stocks in downtrends get rejected at VWAP.
- For stocks trending up (above VWAP, strong open): buy when price pulls back to VWAP
- For stocks trending down (below VWAP, weak open): short when price rallies to VWAP
- Enter within 0.1% of VWAP
- Stop: 0.3% through VWAP on the wrong side
- Target: Previous high/low of the day
- Best between 10:00 AM - 2:00 PM (midday mean reversion)
- **Position size: 10-15% of portfolio per trade**

### 5. Overnight Swing (`strategies/overnight_swing.py`)
**Idea:** Stocks with strong momentum into the close tend to gap up the next morning.
- At 3:30 PM, scan for stocks up > 3% on the day with volume > 2x average
- Confirm uptrend: above VWAP, above all intraday moving averages
- Buy at 3:45 PM, hold overnight
- Sell at next day's open + 15 minutes
- Stop: Pre-set at -2% from entry (as a safety net for gap-down)
- This is the **highest risk/reward strategy** — big gap-ups or big gap-downs
- **Position size: 20-25% of portfolio per trade, max 2 overnight positions**

### 6. Unusual Volume / News Momentum (`strategies/news_momentum.py`)
**Idea:** Stocks with sudden volume spikes often run for hours. Volume precedes price.
- Detect: RVOL > 5.0 with price acceleration
- No need to know the news — the volume IS the signal
- Enter in the direction of the move
- Trail with 1% trailing stop
- Hold as long as volume stays elevated (RVOL > 3.0)
- Exit when volume dries up (RVOL drops below 2.0) or stop is hit
- **Position size: 15% of portfolio per trade**

### 7. Aggressor Meta-Strategy (`strategies/aggressor.py`)
**THIS IS THE PRIMARY PRODUCTION STRATEGY.**
- Collects signals from all 6 strategies above
- Ranks signals by conviction score:
  - +2 if multiple strategies agree on same stock + direction
  - +1 for RVOL > 5
  - +1 for strong trend alignment (above all MAs for longs)
  - +1 if stock is a top-3 gapper of the day
- Take the top 3-5 highest conviction signals
- Size positions aggressively: 15-25% per position
- Total exposure can reach 100%+ if Alpaca allows margin on paper account
- Rotate capital fast: close losers immediately, redeploy into new signals

---

## Backtesting Specifications

### `backtesting/engine.py`
- Use **1-minute bar data** from yfinance or Alpaca for recent history (last 30-60 days)
- Simulate realistic intraday execution:
  - Entry 1 bar after signal (no instant fill)
  - Slippage: 0.05% for liquid stocks, 0.15% for less liquid
  - Commission: $0 (Alpaca is commission-free)
- Track intraday equity curve with minute-level granularity
- Run each strategy independently, then run the aggressor ensemble

### `backtesting/metrics.py`
Short-term metrics that matter:
- **Total P&L ($ and %)** over the backtest period
- **Best single day and worst single day**
- **Win rate and average win vs average loss**
- **Profit factor** (gross profit / gross loss)
- **Max intraday drawdown**
- **Average hold time**
- **Trades per day**
- **Sharpe ratio (annualized from daily returns)**
- **Expectancy per trade** (average P&L per trade)

---

## Risk Management — Aggressive but Not Reckless

### `risk/manager.py`
- **Max position size**: 25% of portfolio per stock
- **Max simultaneous positions**: 5
- **Max total exposure**: 100% (can use full capital)
- **Daily loss limit**: -5% → halt all new trades for the day, close all positions
- **Per-trade risk**: Max 2% of portfolio loss per individual trade (enforced via stop-loss)
- **Drawdown circuit breaker**: -15% from starting capital → system goes flat and stops trading
- **Winning day rule**: If up > 3% on the day, tighten all stops to breakeven (lock in gains)

### `risk/stop_loss.py`
- Every position MUST have a stop-loss. No exceptions.
- Intraday stops: typically 0.5-2% depending on strategy
- Overnight stops: 2-3% from entry
- Trailing stops activate once position is up > 1%
- Hard stop on total portfolio: if account drops below 85% of starting value, everything closes

### `risk/sizing.py`
Position sizing approach:
1. **Fixed fractional**: Risk 2% of portfolio per trade, with stop distance determining share count
2. **Volatility-adjusted**: Size inversely to ATR (more volatile = smaller position)
3. **Kelly criterion (half-Kelly)**: Use recent win rate and win/loss ratio to calculate optimal size, then use half that (full Kelly is too aggressive even for this system)
4. **Scale-in logic**: Start at 60% of target size, add remaining 40% only if trade moves in your favor

---

## Execution Specifications

### `execution/trader.py`
- Use **market orders** for momentum entries (speed matters more than price for surges)
- Use **limit orders** for mean-reversion entries (VWAP bounce, gap fade)
- Implement **OCO (one-cancels-other)** bracket orders: entry + stop-loss + take-profit
- If Alpaca doesn't support OCO natively, simulate with monitoring loop
- Cancel unfilled limit orders after 30 seconds
- Log every execution with microsecond timestamps

### `execution/scheduler.py`
Aggressive intraday schedule:
- **7:00 AM ET**: Fetch pre-market data, run scanner, identify gappers
- **9:25 AM ET**: Final pre-market scan, prepare orders
- **9:30 AM ET**: Market open — monitor but don't trade (let chaos settle)
- **9:35-9:45 AM ET**: Opening range forming — calculate levels
- **9:45 AM ET**: Opening range breakout signals fire. Gap fade signals fire.
- **Every 1 minute, 9:45 AM - 3:30 PM**: Run momentum surge, VWAP bounce, unusual volume scans
- **3:30 PM ET**: Run overnight swing scanner
- **3:45 PM ET**: Enter overnight positions if signals present
- **3:55 PM ET**: Close all intraday-only positions
- **4:00 PM ET**: Market close — generate daily report
- **Respect market holidays** via Alpaca calendar API

### `execution/monitor.py`
- Check all open positions every 30 seconds
- Update trailing stops in real-time
- Track live P&L per position and total
- Trigger alerts for: stop hit, target hit, new signal, circuit breaker
- WebSocket connection to Alpaca for real-time quote updates if available

---

## Dashboard Specifications

### Design Direction
**War room aesthetic** — dark background, neon accents, real-time tickers, urgency. Think trading floor meets cyberpunk. Dense information, fast updates, clear P&L visibility.

**Color scheme:**
- Background: near-black (#0a0a0f)
- Profit: electric green (#00ff88)
- Loss: hot red (#ff3366)
- Neutral/text: cool gray (#8892a0)
- Accent: electric blue (#00aaff)
- Warning: amber (#ffaa00)

### Dashboard Sections

1. **Top Bar — Account Vitals**
   - Portfolio value (large, prominent)
   - Today's P&L in $ and % (color-coded, flashing on update)
   - Cash / Buying power
   - System status: SCANNING / TRADING / HALTED / CIRCUIT BREAKER

2. **Live Positions (center, main area)**
   - Table: Symbol, Direction (LONG/SHORT), Shares, Entry, Current, P&L $, P&L %, Stop, Target
   - Rows glow green/red based on P&L
   - Click to see strategy that generated the signal

3. **Equity Curve (right side)**
   - Intraday equity curve updating every minute
   - Show today's high-water mark
   - Overlay: daily loss limit line, circuit breaker line

4. **Scanner Feed (left side)**
   - Live stream of stocks being detected by scanner
   - Show: Symbol, RVOL, % change, signal type
   - New entries slide in from top

5. **Trade Log (bottom)**
   - Scrolling list of today's completed trades
   - Timestamp, Symbol, Direction, Entry, Exit, P&L, Hold Time, Strategy
   - Running total P&L

6. **Risk Dashboard (collapsible panel)**
   - Current drawdown from starting capital
   - Number of trades today
   - Win/loss count and rate
   - Average win vs average loss
   - Distance to daily loss limit
   - Distance to circuit breaker

**Refresh:** Every 10 seconds during market hours. WebSocket for position updates if possible.

---

## Reporting Specifications

### `reporting/performance.py`
End-of-day report:
- Total P&L ($ and %)
- Number of trades, win rate
- Best trade and worst trade
- Strategy breakdown: which strategy contributed what
- Risk metrics: max drawdown of the day, closest to daily loss limit
- Output to console + save HTML report

### `reporting/trade_log.py`
- SQLite database of all trades
- Fields: id, timestamp_open, timestamp_close, symbol, direction, strategy, shares, entry_price, exit_price, pnl_dollars, pnl_percent, hold_time_minutes, exit_reason (target/stop/time/manual)

### `reporting/alerts.py`
Console alerts with timestamps for:
- New position opened
- Position closed (with P&L)
- Stop-loss triggered
- Daily loss limit approaching (> -3%)
- Circuit breaker triggered
- Scanner detected high-conviction setup

---

## Implementation Order

1. **Phase 1 — Foundation**: config.py, .env, data/fetcher.py, data/indicators.py, data/scanner.py, data/universe.py
2. **Phase 2 — Strategies**: base.py, then opening_range.py and momentum_surge.py first (highest expected value), then the rest
3. **Phase 3 — Backtesting**: engine.py (minute-bar level), metrics.py, run_backtest.py — **backtest on last 30 days of data**
4. **Phase 4 — Risk**: manager.py, stop_loss.py, sizing.py
5. **Phase 5 — Execution**: trader.py, scheduler.py, monitor.py
6. **Phase 6 — Aggressor**: aggressor.py meta-strategy that combines everything
7. **Phase 7 — Dashboard**: app.py, templates, static assets
8. **Phase 8 — Reporting**: performance.py, trade_log.py, alerts.py
9. **Phase 9 — Integration**: main.py wires everything, end-to-end paper trading test

---

## Configuration Defaults (`config.py`)

```python
# Scanner settings
SCANNER_MIN_GAP_PCT = 3.0
SCANNER_MIN_RVOL = 3.0
SCANNER_MIN_PRICE = 5.0
SCANNER_MAX_PRICE = 200.0
SCANNER_MIN_AVG_VOLUME = 1_000_000

# Risk limits
MAX_POSITION_PCT = 0.25
MAX_SIMULTANEOUS_POSITIONS = 5
MAX_TOTAL_EXPOSURE = 1.00
DAILY_LOSS_LIMIT = -0.05
PER_TRADE_RISK = 0.02
CIRCUIT_BREAKER_PCT = -0.15
PROFIT_LOCK_THRESHOLD = 0.03

# Execution
MARKET_ORDER_STRATEGIES = ["momentum_surge", "news_momentum", "opening_range"]
LIMIT_ORDER_STRATEGIES = ["gap_fade", "vwap_bounce"]
LIMIT_ORDER_TIMEOUT_SEC = 30
OVERNIGHT_MAX_POSITIONS = 2
OVERNIGHT_MAX_EXPOSURE = 0.50

# Backtesting
BACKTEST_DAYS = 30
INTRADAY_BAR_SIZE = "1Min"
SLIPPAGE_LIQUID = 0.0005
SLIPPAGE_ILLIQUID = 0.0015

# Scheduling (Eastern Time)
PREMARKET_SCAN_TIME = "07:00"
FINAL_SCAN_TIME = "09:25"
MARKET_OPEN = "09:30"
FIRST_TRADE_TIME = "09:45"
OVERNIGHT_SCAN_TIME = "15:30"
CLOSE_INTRADAY_TIME = "15:55"
MARKET_CLOSE = "16:00"

# Dashboard
DASHBOARD_PORT = 8050
REFRESH_INTERVAL_SEC = 10

# Sizing
KELLY_FRACTION = 0.5
SCALE_IN_INITIAL = 0.60
SCALE_IN_ADD = 0.40
SCALE_IN_THRESHOLD = 0.01
```

---

## Key Principles for This System

1. **Speed over perfection** — In short-term trading, being approximately right and fast beats being precisely right and slow
2. **Cut losers ruthlessly** — Every position has a stop. No hoping, no averaging down on losers.
3. **Let winners run (briefly)** — Use trailing stops, not fixed targets, for momentum trades
4. **Volume is truth** — Volume surges are the most reliable short-term signal. Price can lie, volume can't.
5. **The first and last hour are where money is made** — Concentrate activity in 9:30-10:30 and 3:00-4:00
6. **No overnight without conviction** — Only the strongest setups get held overnight, max 2 positions
7. **Respect the circuit breaker** — The -5% daily halt and -15% total halt exist to prevent catastrophic loss. Never override them.
8. **This is paper trading** — Experiment aggressively, learn from the results, treat losses as tuition

---

## Testing

- Backtest each strategy on the last 30 days of 1-minute data
- Verify scanner correctly identifies pre-market gappers using historical data
- Test risk manager: simulate a -5% day and confirm halt triggers
- Test circuit breaker: simulate -15% drawdown and confirm full liquidation
- Paper trade for at least 5 full trading days before trusting any results
- Compare vs SPY over the same period — that's the real benchmark
