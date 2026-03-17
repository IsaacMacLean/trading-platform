"""
End-of-day performance report.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import pytz
from loguru import logger

ET = pytz.timezone("America/New_York")


def generate_eod_report(trades: List[dict], account) -> Dict:
    """
    Generate end-of-day performance report.
    Prints summary to console and saves HTML report.

    trades: list of trade dicts from TradeLogger.get_today_trades()
    account: Alpaca account object
    """
    now_str = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S ET")

    equity = float(getattr(account, "equity", 0))
    last_equity = float(getattr(account, "last_equity", equity))
    day_pnl = equity - last_equity
    day_pnl_pct = day_pnl / last_equity * 100 if last_equity > 0 else 0.0

    # Trade stats
    total_trades = len(trades)
    wins = [t for t in trades if (t.get("pnl_dollars") or 0) > 0]
    losses = [t for t in trades if (t.get("pnl_dollars") or 0) < 0]
    win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0.0
    avg_win = sum(t.get("pnl_dollars", 0) for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.get("pnl_dollars", 0) for t in losses) / len(losses) if losses else 0.0

    best_trade = max(trades, key=lambda t: t.get("pnl_dollars", 0), default={})
    worst_trade = min(trades, key=lambda t: t.get("pnl_dollars", 0), default={})

    # Strategy breakdown
    strategy_pnl: Dict[str, float] = {}
    for t in trades:
        strat = t.get("strategy", "unknown")
        strategy_pnl[strat] = strategy_pnl.get(strat, 0) + t.get("pnl_dollars", 0)

    metrics = {
        "timestamp": now_str,
        "equity": equity,
        "last_equity": last_equity,
        "day_pnl": day_pnl,
        "day_pnl_pct": day_pnl_pct,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "strategy_breakdown": strategy_pnl,
    }

    # Console output
    sep = "=" * 55
    logger.info(sep)
    logger.info("       END-OF-DAY PERFORMANCE REPORT")
    logger.info(sep)
    logger.info(f"  Date/Time  : {now_str}")
    logger.info(f"  Equity     : ${equity:,.2f}")
    logger.info(f"  Day P&L    : ${day_pnl:+,.2f}  ({day_pnl_pct:+.2f}%)")
    logger.info(f"  Trades     : {total_trades}  (W:{len(wins)}  L:{len(losses)}  WR:{win_rate:.1f}%)")
    logger.info(f"  Avg Win    : ${avg_win:+,.2f}")
    logger.info(f"  Avg Loss   : ${avg_loss:+,.2f}")
    if best_trade:
        logger.info(f"  Best Trade : {best_trade.get('symbol','')} ${best_trade.get('pnl_dollars',0):+,.2f}")
    if worst_trade:
        logger.info(f"  Worst Trade: {worst_trade.get('symbol','')} ${worst_trade.get('pnl_dollars',0):+,.2f}")
    logger.info("  Strategy Breakdown:")
    for s, p in strategy_pnl.items():
        logger.info(f"    {s:<25}: ${p:+,.2f}")
    logger.info(sep)

    # Save HTML
    html_path = f"eod_report_{datetime.now(ET).strftime('%Y%m%d')}.html"
    _save_html(metrics, trades, html_path)

    return metrics


def _save_html(metrics: Dict, trades: List[dict], path: str) -> None:
    """Save an HTML EOD report."""
    now_str = metrics.get("timestamp", "")
    day_pnl = metrics.get("day_pnl", 0)
    day_pct = metrics.get("day_pnl_pct", 0)
    pnl_color = "#00ff88" if day_pnl >= 0 else "#ff3366"

    trade_rows = ""
    for t in trades:
        pnl = t.get("pnl_dollars", 0)
        c = "#00ff88" if pnl >= 0 else "#ff3366"
        trade_rows += f"""<tr>
          <td>{t.get('timestamp_close','')[:19]}</td>
          <td>{t.get('symbol','')}</td>
          <td>{t.get('direction','')}</td>
          <td>{t.get('strategy','')}</td>
          <td>${t.get('entry_price',0):.2f}</td>
          <td>${t.get('exit_price',0):.2f}</td>
          <td>{t.get('shares',0)}</td>
          <td style="color:{c}">${pnl:+,.2f}</td>
          <td>{t.get('exit_reason','')}</td>
          <td>{int(t.get('hold_time_minutes',0))}m</td>
        </tr>"""

    strat_rows = ""
    for s, p in metrics.get("strategy_breakdown", {}).items():
        c = "#00ff88" if p >= 0 else "#ff3366"
        strat_rows += f"<tr><td>{s}</td><td style='color:{c}'>${p:+,.2f}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>EOD Report — {now_str}</title>
  <style>
    body{{background:#0a0a0f;color:#8892a0;font-family:'Courier New',monospace;padding:20px}}
    h1,h2{{color:#00aaff}}
    .card{{background:#0f0f1a;border:1px solid #1a1a2e;border-radius:8px;padding:20px;margin:10px 0}}
    .big{{font-size:28px;font-weight:bold}}
    table{{width:100%;border-collapse:collapse;font-size:11px}}
    th{{color:#00aaff;padding:6px;border-bottom:1px solid #1a1a2e;text-align:left}}
    td{{padding:5px 6px;border-bottom:1px solid #1a1a2e}}
  </style>
</head>
<body>
  <h1>End-of-Day Report</h1>
  <p>{now_str}</p>
  <div class="card">
    <h2>Summary</h2>
    <div class="big" style="color:{pnl_color}">${day_pnl:+,.2f} ({day_pct:+.2f}%)</div>
    <p>Equity: ${metrics.get('equity',0):,.2f} &nbsp;|&nbsp;
       Trades: {metrics.get('total_trades',0)} &nbsp;|&nbsp;
       Win Rate: {metrics.get('win_rate',0):.1f}%</p>
    <p>Avg Win: ${metrics.get('avg_win',0):+,.2f} &nbsp;|&nbsp;
       Avg Loss: ${metrics.get('avg_loss',0):+,.2f}</p>
  </div>
  <div class="card">
    <h2>Strategy Breakdown</h2>
    <table><tr><th>Strategy</th><th>P&L</th></tr>{strat_rows}</table>
  </div>
  <div class="card">
    <h2>Trades</h2>
    <table>
      <tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Strategy</th>
          <th>Entry</th><th>Exit</th><th>Qty</th><th>P&L</th><th>Reason</th><th>Hold</th></tr>
      {trade_rows}
    </table>
  </div>
</body>
</html>"""

    try:
        with open(path, "w") as f:
            f.write(html)
        logger.info(f"EOD report saved: {path}")
    except Exception as exc:
        logger.error(f"_save_html: {exc}")
