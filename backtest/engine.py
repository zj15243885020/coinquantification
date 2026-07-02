"""事件驱动回测引擎 - 严格禁止前瞻偏差"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from strategy.base import Signal, SignalType, Strategy


@dataclass
class BacktestTrade:
    """回测交易记录"""
    entry_time: datetime
    exit_time: datetime | None = None
    symbol: str = ""
    side: str = "long"
    entry_price: float = 0.0
    exit_price: float | None = None
    size: float = 0.0
    commission: float = 0.0
    slippage_cost: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    is_open: bool = True


@dataclass
class BacktestState:
    """回测状态"""
    initial_capital: float = 10000.0
    equity: float = 10000.0
    cash: float = 10000.0
    position: BacktestTrade | None = None
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


class BacktestEngine:
    """事件驱动回测引擎

    核心设计原则：
    1. 逐 bar 推进，bar[i] 只能访问 bars[0..i] 的数据
    2. 内置手续费模型（Maker/Taker）
    3. 内置滑点模拟
    4. 信号在当前 bar 收盘时生成，下一 bar 开盘价执行
    """

    def __init__(
        self,
        strategy: Strategy,
        initial_capital: float = 10000.0,
        commission_maker: float = 0.0002,
        commission_taker: float = 0.0005,
        slippage_model: str = "fixed",
        slippage_value: float = 0.0001,
        position_size_pct: float = 0.1,
    ):
        self.strategy = strategy
        self.state = BacktestState(
            initial_capital=initial_capital,
            equity=initial_capital,
            cash=initial_capital,
        )
        self.commission_maker = commission_maker
        self.commission_taker = commission_taker
        self.slippage_model = slippage_model
        self.slippage_value = slippage_value
        self.position_size_pct = position_size_pct

    def _calculate_slippage(self, price: float, side: str) -> float:
        """计算滑点"""
        if self.slippage_model == "fixed":
            slip = price * self.slippage_value
        else:
            slip = price * self.slippage_value
        return slip if side == "long" else -slip

    def _calculate_commission(self, notional: float, is_maker: bool = False) -> float:
        """计算手续费"""
        rate = self.commission_maker if is_maker else self.commission_taker
        return notional * rate

    def _execute_signal(self, signal: Signal, exec_price: float) -> None:
        """执行信号 - 在下一 bar 开盘价成交"""
        slipped_price = exec_price + self._calculate_slippage(exec_price, signal.signal_type.value)

        if signal.is_entry:
            if self.state.position and self.state.position.is_open:
                self._close_position(slipped_price, signal.timestamp)

            side = "long" if signal.signal_type == SignalType.LONG else "short"
            alloc = self.state.equity * self.position_size_pct
            size = alloc / slipped_price
            commission = self._calculate_commission(alloc)

            trade = BacktestTrade(
                entry_time=signal.timestamp,
                symbol=signal.symbol,
                side=side,
                entry_price=slipped_price,
                size=size,
                commission=commission,
                slippage_cost=abs(slipped_price - exec_price) * size,
            )
            self.state.position = trade
            self.state.cash -= alloc + commission

        elif signal.is_exit:
            if self.state.position and self.state.position.is_open:
                self._close_position(slipped_price, signal.timestamp)

    def _close_position(self, exit_price: float, exit_time: datetime) -> None:
        """平仓"""
        pos = self.state.position
        if pos is None:
            return

        pos.exit_time = exit_time
        pos.exit_price = exit_price

        if pos.side == "long":
            raw_pnl = (exit_price - pos.entry_price) * pos.size
        else:
            raw_pnl = (pos.entry_price - exit_price) * pos.size

        exit_commission = self._calculate_commission(exit_price * pos.size)
        pos.commission += exit_commission
        pos.pnl = raw_pnl - pos.commission
        pos.pnl_pct = pos.pnl / (pos.entry_price * pos.size) if pos.entry_price * pos.size > 0 else 0.0
        pos.is_open = False

        self.state.cash += pos.entry_price * pos.size + pos.pnl
        self.state.trades.append(pos)
        self.state.position = None

    def _update_equity(self, current_price: float) -> None:
        """更新权益"""
        unrealized = 0.0
        if self.state.position and self.state.position.is_open:
            pos = self.state.position
            if pos.side == "long":
                unrealized = (current_price - pos.entry_price) * pos.size
            else:
                unrealized = (pos.entry_price - current_price) * pos.size
        self.state.equity = self.state.cash + (
            self.state.position.entry_price * self.state.position.size + unrealized
            if self.state.position and self.state.position.is_open
            else 0.0
        )

    def run(self, bars: pd.DataFrame) -> BacktestState:
        """运行回测

        Args:
            bars: K 线 DataFrame，必须包含 timestamp/open/high/low/close/volume 列

        Returns:
            BacktestState 包含完整回测结果
        """
        if bars.empty:
            return self.state

        self.strategy.calculate_indicators(bars, len(bars) - 1)

        pending_signal: Signal | None = None

        for i in range(len(bars)):
            bar = bars.iloc[i]
            current_price = float(bar["close"])

            if pending_signal is not None and i > 0:
                exec_price = float(bars.iloc[i]["open"])
                self._execute_signal(pending_signal, exec_price)
                self.state.signals.append(pending_signal)
                pending_signal = None

            signal = self.strategy.on_bar(i, bars)
            if signal is not None:
                pending_signal = signal

            self._update_equity(current_price)

            self.state.equity_curve.append({
                "timestamp": bar["timestamp"],
                "equity": self.state.equity,
                "cash": self.state.cash,
                "price": current_price,
            })

        if pending_signal is not None:
            self.state.signals.append(pending_signal)

        if self.state.position and self.state.position.is_open:
            last_price = float(bars.iloc[-1]["close"])
            self._close_position(last_price, bars.iloc[-1]["timestamp"].to_pydatetime())

        return self.state
