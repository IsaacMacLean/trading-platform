"""
Backtest results display — print summary and save HTML report.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict

import pandas as pd
from loguru import logger


def print_results(metrics: Dict) -> None:
    """Print a formatted backtest results summary to console."""
    sep = "=" * 60
    print(f"\n{sep}")
    print("           BACKTEST RESULTS SUMMARY")
    print(sep)
    print(f"  Initial Equity  : ${metrics.get('initial_equity', 0):>12,.2f}")
    print(f"  Final Equity    : ${metrics.get('final_equity', 0):>12,.2f}")
    print(f"  Total P&L       : ${metrics.get('total_pnl', 0):>+12,.2f}  ({metrics.get('total_pnl_pct', 0):+.2f}%)")
    print(f"  Best Day        : {metrics.get('best_day_pct', 0):>+.2f}%")
    print(f"  Worst Day       : {metrics.get('worst_day_pct', 0):>+.2f}%")
    print()
    print(f"  Total Trades    : {metrics.get('total_trades', 0)}")
    print(f"  Trades/Day      : {metrics.get('trades_per_day', 0):.1f}")
    print(f"  Win Rate        : {metrics.get('win_rate', 0):.1f}%  ({metrics.get('num_wins', 0)}W / {metrics.get('num_losses', 0)}L)")
    print(f"  Avg Win         : ${metrics.get('avg_win', 0):>+,.2f}")
    print(f"  Avg Loss        : ${metrics.get('avg_loss', 0):>+,.2f}")
    print(f"  Largest Win     : ${metrics.get('largest_win', 0):>+,.2f}")
    print(f"  Largest Loss    : ${metrics.get('largest_loss', 0):>+,.2f}")
    print(f"  Profit Factor   : {metrics.get('profit_factor', 0):.2f}")
    print(f"  Expectancy/Trade: ${metrics.get('expectancy', 0):>+,.2f}")
    print()
    print(f"  Max Drawdown    : {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Sharpe Ratio    : {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"  Avg Hold Time   : {metrics.get('avg_hold_minutes', 0):.0f} min")
    print()

    if "strategy_breakdown" in metrics:
        print("  Strategy P&L Breakdown:")
        for strat, pnl in metrics["strategy_breakdown"].items():
            print(f"    {strat:<25}: ${pnl:>+,.2f}")
        print()

    print(sep)


def save_html_report(metrics: Dict, trades_df: pd.DataFrame, path: str = "backtest_report.html") -> None:
    """Save a styled HTML backtest report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    trade_rows = ""
    if trades_df is not None and not trades_df.empty:
        for _, row in trades_df.iterrows():
            pnl = row.get("pnl", 0)
            color = "#00ff88" if pnl >= 0 else "#ff3366"
            trade_rows += f"""
            <tr style="border-bottom:1px solid #1a1a2e;">
              <td>{str(row.get('entry_time', ''))[:19]}</td>
              <td>{row.get('symbol', '')}</td>
              <td>{row.get('strategy', '')}</td>
              <td>{row.get('direction', '')}</td>
              <td>${row.get('entry_price', 0):.2f}</td>
              <td>${row.get('exit_price', 0):.2f}</td>
              <td>{row.get('qty', 0)}</td>
              <td style="color:{color}">${pnl:+,.2f}</td>
              <td>{row.get('exit_reason', '')}</td>
              <td>{row.get('hold_minutes', 0):.0f}m</td>
            </tr>"""

    strategy_rows = ""
    for strat, pnl in metrics.get("strategy_breakdown", {}).items():
        color = "#00ff88" if pnl >= 0 else "#ff3366"
        strategy_rows += f"""
        <tr>
          <td>{strat}</td>
          <td style="color:{color}">${pnl:+,.2f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Backtest Report — {timestamp}</title>
  <style>
    body {{ background:#0a0a0f; color:#8892a0; font-family:'Courier New',monospace; margin:0; padding:20px; }}
    h1,h2,h3 {{ color:#00aaff; }}
    .card {{ background:#0f0f1a; border:1px solid #1a1a2e; border-radius:8px; padding:20px; margin:15px 0; }}
    .metric {{ display:inline-block; margin:10px 20px 10px 0; }}
    .metric .label {{ font-size:12px; color:#8892a0; }}
    .metric .value {{ font-size:24px; font-weight:bold; }}
    .positive {{ color:#00ff88; }}
    .negative {{ color:#ff3366; }}
    .neutral {{ color:#00aaff; }}
    table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    th {{ color:#00aaff; padding:8px; text-align:left; border-bottom:1px solid #1a1a2e; }}
    td {{ padding:6px 8px; }}
  </style>
</head>
<body>
  <h1>Backtest Report</h1>
  <p style="color:#8892a0">Generated: {timestamp}</p>

  <div class="card">
    <h2>Performance Summary</h2>
    <div class="metric">
      <div class="label">Total P&L</div>
      <div class="value {'positive' if metrics.get('total_pnl', 0) >= 0 else 'negative'}">
        ${metrics.get('total_pnl', 0):+,.2f} ({metrics.get('total_pnl_pct', 0):+.2f}%)
      </div>
    </div>
    <div class="metric">
      <div class="label">Final Equity</div>
      <div class="value neutral">${metrics.get('final_equity', 0):,.2f}</div>
    </div>
    <div class="metric">
      <div class="label">Sharpe Ratio</div>
      <div class="value neutral">{metrics.get('sharpe_ratio', 0):.2f}</div>
    </div>
    <div class="metric">
      <div class="label">Max Drawdown</div>
      <div class="value negative">{metrics.get('max_drawdown_pct', 0):.2f}%</div>
    </div>
    <div class="metric">
      <div class="label">Win Rate</div>
      <div class="value positive">{metrics.get('win_rate', 0):.1f}%</div>
    </div>
    <div class="metric">
      <div class="label">Profit Factor</div>
      <div class="value neutral">{metrics.get('profit_factor', 0):.2f}</div>
    </div>
    <div class="metric">
      <div class="label">Total Trades</div>
      <div class="value neutral">{metrics.get('total_trades', 0)}</div>
    </div>
    <div class="metric">
      <div class="label">Expectancy/Trade</div>
      <div class="value {'positive' if metrics.get('expectancy', 0) >= 0 else 'negative'}">${metrics.get('expectancy', 0):+,.2f}</div>
    </div>
  </div>

  <div class="card">
    <h2>Strategy Breakdown</h2>
    <table>
      <tr><th>Strategy</th><th>P&L</th></tr>
      {strategy_rows}
    </table>
  </div>

  <div class="card">
    <h2>Trade Log ({metrics.get('total_trades', 0)} trades)</h2>
    <table>
      <tr>
        <th>Time</th><th>Symbol</th><th>Strategy</th><th>Dir</th>
        <th>Entry</th><th>Exit</th><th>Qty</th><th>P&L</th>
        <th>Reason</th><th>Hold</th>
      </tr>
      {trade_rows}
    </table>
  </div>
</body>
</html>"""

    try:
        with open(path, "w") as f:
            f.write(html)
        logger.info(f"Backtest HTML report saved: {path}")
    except Exception as exc:
        logger.error(f"save_html_report: {exc}")
