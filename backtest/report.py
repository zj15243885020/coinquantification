"""回测报告生成 - 关键指标计算 + HTML 图表"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest.engine import BacktestState, BacktestTrade


def calculate_metrics(state: BacktestState) -> dict[str, Any]:
    """计算回测关键指标"""
    trades = [t for t in state.trades if not t.is_open]
    if not trades:
        return {
            "total_trades": 0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_pnl": 0.0,
            "total_commission": 0.0,
            "total_slippage": 0.0,
        }

    pnls = [t.pnl for t in trades]
    pnl_pcts = [t.pnl_pct for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    equity_series = pd.Series([e["equity"] for e in state.equity_curve])
    peak = equity_series.cummax()
    drawdown = (equity_series - peak) / peak
    max_dd = float(drawdown.min())

    returns = equity_series.pct_change().dropna()
    sharpe = 0.0
    if len(returns) > 1 and returns.std() > 0:
        sharpe = float(returns.mean() / returns.std() * np.sqrt(252))

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total_return = (state.equity - state.initial_capital) / state.initial_capital

    return {
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "total_return_pct": round(total_return * 100, 2),
        "max_drawdown_pct": round(abs(max_dd) * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": round(profit_factor, 2),
        "avg_pnl": round(np.mean(pnls), 2),
        "avg_pnl_pct": round(np.mean(pnl_pcts) * 100, 4),
        "total_commission": round(sum(t.commission for t in trades), 2),
        "total_slippage": round(sum(t.slippage_cost for t in trades), 2),
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
        "final_equity": round(state.equity, 2),
    }


def generate_report(state: BacktestState, output_path: str | Path = "backtest_report.html") -> Path:
    """生成 HTML 回测报告"""
    metrics = calculate_metrics(state)
    equity_df = pd.DataFrame(state.equity_curve)
    trades_data = []
    for t in state.trades:
        trades_data.append({
            "entry_time": str(t.entry_time),
            "exit_time": str(t.exit_time) if t.exit_time else "open",
            "symbol": t.symbol,
            "side": t.side,
            "entry_price": round(t.entry_price, 2),
            "exit_price": round(t.exit_price, 2) if t.exit_price else None,
            "size": round(t.size, 6),
            "pnl": round(t.pnl, 2),
            "pnl_pct": round(t.pnl_pct * 100, 4),
            "commission": round(t.commission, 4),
        })

    equity_json = equity_df.to_json(orient="records", date_format="iso") if not equity_df.empty else "[]"
    trades_json = json.dumps(trades_data)
    metrics_json = json.dumps(metrics, indent=2)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>回测报告 - {state.trades[0].symbol if state.trades else 'N/A'}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #0d1117; color: #c9d1d9; }}
  h1 {{ color: #58a6ff; }}
  .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 20px 0; }}
  .metric {{ background: #161b22; padding: 16px; border-radius: 8px; border: 1px solid #30363d; }}
  .metric .label {{ color: #8b949e; font-size: 12px; }}
  .metric .value {{ font-size: 24px; font-weight: bold; margin-top: 4px; }}
  .positive {{ color: #3fb950; }}
  .negative {{ color: #f85149; }}
  .chart-container {{ background: #161b22; padding: 20px; border-radius: 8px; margin: 20px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; }}
  th {{ color: #8b949e; font-size: 12px; }}
</style>
</head>
<body>
<h1>回测报告</h1>
<div class="metrics">
  <div class="metric"><div class="label">总收益率</div><div class="value {'positive' if metrics['total_return_pct'] >= 0 else 'negative'}">{metrics['total_return_pct']}%</div></div>
  <div class="metric"><div class="label">最大回撤</div><div class="value negative">{metrics['max_drawdown_pct']}%</div></div>
  <div class="metric"><div class="label">夏普比率</div><div class="value">{metrics['sharpe_ratio']}</div></div>
  <div class="metric"><div class="label">胜率</div><div class="value">{metrics['win_rate']}%</div></div>
  <div class="metric"><div class="label">盈亏比</div><div class="value">{metrics['profit_factor']}</div></div>
  <div class="metric"><div class="label">总交易次数</div><div class="value">{metrics['total_trades']}</div></div>
  <div class="metric"><div class="label">总手续费</div><div class="value">${metrics['total_commission']}</div></div>
  <div class="metric"><div class="label">最终权益</div><div class="value">${metrics['final_equity']}</div></div>
</div>
<div class="chart-container"><canvas id="equityChart"></canvas></div>
<h2>交易记录</h2>
<table>
<tr><th>入场时间</th><th>出场时间</th><th>方向</th><th>入场价</th><th>出场价</th><th>数量</th><th>盈亏</th><th>盈亏%</th></tr>
"""
    for t in trades_data:
        pnl_class = "positive" if t["pnl"] >= 0 else "negative"
        html += f"""<tr>
<td>{t['entry_time']}</td><td>{t['exit_time']}</td><td>{t['side']}</td>
<td>{t['entry_price']}</td><td>{t['exit_price']}</td><td>{t['size']}</td>
<td class="{pnl_class}">{t['pnl']}</td><td class="{pnl_class}">{t['pnl_pct']}%</td>
</tr>"""

    html += f"""</table>
<script>
const equityData = {equity_json};
const ctx = document.getElementById('equityChart').getContext('2d');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: equityData.map(d => d.timestamp),
    datasets: [{{
      label: '权益曲线',
      data: equityData.map(d => d.equity),
      borderColor: '#58a6ff',
      fill: false,
      pointRadius: 0,
    }}, {{
      label: '价格',
      data: equityData.map(d => d.price),
      borderColor: '#8b949e',
      fill: false,
      pointRadius: 0,
      yAxisID: 'y1',
    }}]
  }},
  options: {{
    responsive: true,
    scales: {{
      y: {{ position: 'left', title: {{ display: true, text: '权益 (USDT)' }} }},
      y1: {{ position: 'right', title: {{ display: true, text: '价格' }}, grid: {{ drawOnChartArea: false }} }}
    }}
  }}
}});
</script>
</body></html>"""

    output = Path(output_path)
    output.write_text(html, encoding="utf-8")
    return output


def print_summary(state: BacktestState) -> str:
    """打印回测摘要"""
    metrics = calculate_metrics(state)
    lines = [
        "=" * 50,
        "回测结果摘要",
        "=" * 50,
        f"  初始资金:    ${state.initial_capital:,.2f}",
        f"  最终权益:    ${metrics['final_equity']:,.2f}",
        f"  总收益率:    {metrics['total_return_pct']}%",
        f"  最大回撤:    {metrics['max_drawdown_pct']}%",
        f"  夏普比率:    {metrics['sharpe_ratio']}",
        f"  总交易次数:  {metrics['total_trades']}",
        f"  胜率:        {metrics['win_rate']}%",
        f"  盈亏比:      {metrics['profit_factor']}",
        f"  平均盈亏:    ${metrics['avg_pnl']:,.2f}",
        f"  总手续费:    ${metrics['total_commission']:,.2f}",
        f"  总滑点成本:  ${metrics['total_slippage']:,.2f}",
        "=" * 50,
    ]
    return "\n".join(lines)
