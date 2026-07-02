"""单元测试 - 策略引擎与回测"""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timezone

from strategy.base import Signal, SignalType, Strategy
from strategy.examples.dual_ma import DualMAStrategy
from strategy.examples.bollinger_breakout import BollingerBreakoutStrategy
from backtest.engine import BacktestEngine
from backtest.report import calculate_metrics


def generate_test_bars(n: int = 200, trend: str = "up") -> pd.DataFrame:
    """生成测试 K 线数据"""
    np.random.seed(42)
    base_price = 50000.0
    prices = [base_price]
    for i in range(1, n):
        if trend == "up":
            change = np.random.normal(0.001, 0.02)
        elif trend == "down":
            change = np.random.normal(-0.001, 0.02)
        else:
            change = np.random.normal(0, 0.02)
        prices.append(prices[-1] * (1 + change))

    timestamps = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    data = {
        "timestamp": timestamps,
        "open": [p * (1 + np.random.uniform(-0.005, 0.005)) for p in prices],
        "high": [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        "low": [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        "close": prices,
        "volume": np.random.uniform(100, 1000, n),
    }
    return pd.DataFrame(data)


class TestDualMAStrategy:
    def test_generates_signals(self):
        bars = generate_test_bars(200)
        strategy = DualMAStrategy(params={"fast_period": 10, "slow_period": 30, "symbol": "BTC/USDT"})
        strategy.calculate_indicators(bars, len(bars) - 1)

        signals = []
        for i in range(len(bars)):
            signal = strategy.on_bar(i, bars)
            if signal:
                signals.append(signal)

        assert len(signals) > 0

    def test_signal_has_correct_fields(self):
        bars = generate_test_bars(200)
        strategy = DualMAStrategy(params={"fast_period": 10, "slow_period": 30, "symbol": "BTC/USDT"})
        strategy.calculate_indicators(bars, len(bars) - 1)

        for i in range(len(bars)):
            signal = strategy.on_bar(i, bars)
            if signal:
                assert isinstance(signal, Signal)
                assert signal.symbol == "BTC/USDT"
                assert signal.signal_type in (SignalType.LONG, SignalType.SHORT)
                assert signal.price > 0
                break


class TestBollingerBreakoutStrategy:
    def test_generates_signals(self):
        bars = generate_test_bars(200)
        strategy = BollingerBreakoutStrategy(params={"period": 20, "std_dev": 2.0, "symbol": "BTC/USDT"})
        strategy.calculate_indicators(bars, len(bars) - 1)

        signals = []
        for i in range(len(bars)):
            signal = strategy.on_bar(i, bars)
            if signal:
                signals.append(signal)

        assert len(signals) > 0


class TestBacktestEngine:
    def test_backtest_runs_successfully(self):
        bars = generate_test_bars(200)
        strategy = DualMAStrategy(params={"fast_period": 10, "slow_period": 30, "symbol": "BTC/USDT"})

        engine = BacktestEngine(strategy=strategy, initial_capital=10000.0)
        state = engine.run(bars)

        assert len(state.equity_curve) == 200
        assert state.equity > 0

    def test_backtest_no_look_ahead_bias(self):
        """验证前瞻偏差防护 - 策略在 bar[i] 不能访问 bar[i+1]"""
        bars = generate_test_bars(100)
        strategy = DualMAStrategy(params={"fast_period": 5, "slow_period": 10})

        class CheatingStrategy(DualMAStrategy):
            def on_bar(self, bar_index, bars_df):
                self.validate_bar_access(bar_index, bar_index + 1)
                return None

        strategy = CheatingStrategy(params={"fast_period": 5, "slow_period": 10})
        strategy.calculate_indicators(bars, len(bars) - 1)

        with pytest.raises(ValueError, match="Look-ahead bias"):
            strategy.on_bar(50, bars)

    def test_backtest_metrics_calculated(self):
        bars = generate_test_bars(200)
        strategy = DualMAStrategy(params={"fast_period": 10, "slow_period": 30, "symbol": "BTC/USDT"})

        engine = BacktestEngine(strategy=strategy, initial_capital=10000.0)
        state = engine.run(bars)
        metrics = calculate_metrics(state)

        assert "total_trades" in metrics
        assert "total_return_pct" in metrics
        assert "max_drawdown_pct" in metrics
        assert "sharpe_ratio" in metrics
        assert "win_rate" in metrics

    def test_backtest_with_commission_and_slippage(self):
        bars = generate_test_bars(200)
        strategy = DualMAStrategy(params={"fast_period": 10, "slow_period": 30, "symbol": "BTC/USDT"})

        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=10000.0,
            commission_taker=0.001,
            slippage_value=0.001,
        )
        state = engine.run(bars)

        total_commission = sum(t.commission for t in state.trades)
        total_slippage = sum(t.slippage_cost for t in state.trades)
        assert total_commission > 0
        assert total_slippage >= 0

    def test_empty_bars_returns_initial_state(self):
        bars = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        strategy = DualMAStrategy()
        engine = BacktestEngine(strategy=strategy)
        state = engine.run(bars)
        assert state.equity == 10000.0
