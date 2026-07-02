"""单元测试 - 风控引擎"""

import pytest
from datetime import datetime, timezone

from risk.engine import RiskEngine
from risk.allocation import AllocationManager
from strategy.base import Signal, SignalType


def make_signal(price: float = 50000.0, strategy: str = "test") -> Signal:
    return Signal(
        signal_type=SignalType.LONG,
        symbol="BTC/USDT",
        timestamp=datetime.now(timezone.utc),
        price=price,
        metadata={"strategy_name": strategy, "order_size": 0.1},
    )


class TestRiskEngine:
    def test_normal_signal_passes(self):
        engine = RiskEngine(max_position_pct=0.1)
        signal = make_signal()
        allowed, reason = engine.check_signal(signal, equity=100000, current_position_value=0)
        assert allowed is True

    def test_oversized_position_blocked(self):
        engine = RiskEngine(max_position_pct=0.01)
        signal = make_signal(price=50000.0)
        signal.metadata["order_size"] = 1.0
        allowed, reason = engine.check_signal(signal, equity=10000, current_position_value=0)
        assert allowed is False
        assert "exceeds limit" in reason

    def test_daily_loss_circuit_breaker(self):
        engine = RiskEngine(max_daily_loss_pct=0.05, max_position_pct=0.5)
        engine.record_trade_result("test_strategy", -600.0)

        signal = make_signal(strategy="test_strategy")
        allowed, reason = engine.check_signal(signal, equity=10000, current_position_value=0)
        assert allowed is False
        assert "Circuit breaker" in reason or "circuit" in reason.lower()

    def test_consecutive_loss_breaker(self):
        engine = RiskEngine(consecutive_loss_limit=3)
        for _ in range(3):
            engine.record_trade_result("test_strategy", -100.0)

        assert engine.is_circuit_breaker_active("test_strategy") is True

    def test_win_resets_consecutive_losses(self):
        engine = RiskEngine(consecutive_loss_limit=3)
        engine.record_trade_result("test_strategy", -100.0)
        engine.record_trade_result("test_strategy", -100.0)
        engine.record_trade_result("test_strategy", 200.0)

        assert engine.is_circuit_breaker_active("test_strategy") is False

    def test_slippage_check(self):
        engine = RiskEngine(max_slippage_pct=0.005)
        assert engine.check_slippage(50000, 50100) is True
        assert engine.check_slippage(50000, 51000) is False

    def test_reset_circuit_breaker(self):
        engine = RiskEngine(consecutive_loss_limit=2)
        engine.record_trade_result("s1", -100)
        engine.record_trade_result("s1", -100)
        assert engine.is_circuit_breaker_active("s1") is True
        engine.reset_circuit_breaker("s1")
        assert engine.is_circuit_breaker_active("s1") is False


class TestAllocationManager:
    def test_allocate_capital(self):
        mgr = AllocationManager(total_capital=100000)
        alloc = mgr.allocate("strategy_a", 30000)
        assert alloc.allocated_capital == 30000
        assert mgr.available_capital == 70000

    def test_over_allocation_raises(self):
        mgr = AllocationManager(total_capital=10000)
        with pytest.raises(ValueError, match="Insufficient"):
            mgr.allocate("s1", 20000)

    def test_isolated_pools(self):
        mgr = AllocationManager(total_capital=100000)
        mgr.allocate("s1", 30000)
        mgr.allocate("s2", 30000)

        mgr.update_pnl("s1", realized=-5000)
        s1 = mgr.get_allocation("s1")
        s2 = mgr.get_allocation("s2")
        assert s1.realized_pnl == -5000
        assert s2.realized_pnl == 0
