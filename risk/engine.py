"""风控引擎 - 多层风控：仓位限制、日亏损熔断、滑点保护"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Any, Callable

from strategy.base import Signal, SignalType


@dataclass
class RiskEvent:
    """风控事件"""
    event_type: str
    message: str
    timestamp: datetime
    strategy_name: str = ""
    severity: str = "warning"  # warning | critical
    metadata: dict[str, Any] = field(default_factory=dict)


class RiskEngine:
    """风控引擎

    多层防护：
    1. 单笔最大仓位限制
    2. 日最大亏损熔断
    3. 总资金利用率上限
    4. 滑点保护阈值
    5. 连续亏损熔断
    """

    def __init__(
        self,
        max_position_pct: float = 0.1,
        max_daily_loss_pct: float = 0.05,
        max_total_exposure_pct: float = 0.5,
        max_slippage_pct: float = 0.005,
        consecutive_loss_limit: int = 5,
    ):
        self.max_position_pct = max_position_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.max_slippage_pct = max_slippage_pct
        self.consecutive_loss_limit = consecutive_loss_limit

        self._daily_pnl: dict[str, float] = {}
        self._daily_date: str = ""
        self._consecutive_losses: dict[str, int] = {}
        self._circuit_breaker_active: dict[str, bool] = {}
        self._risk_events: list[RiskEvent] = []
        self._alert_callbacks: list[Callable[[RiskEvent], None]] = []

    def on_alert(self, callback: Callable[[RiskEvent], None]) -> None:
        self._alert_callbacks.append(callback)

    def _emit_event(self, event: RiskEvent) -> None:
        self._risk_events.append(event)
        for cb in self._alert_callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def _reset_daily_if_needed(self) -> None:
        today = date.today().isoformat()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_pnl.clear()
            self._consecutive_losses.clear()

    def check_signal(self, signal: Signal, equity: float, current_position_value: float) -> tuple[bool, str]:
        """检查信号是否通过风控

        Returns:
            (allowed, reason) - allowed=False 时 reason 说明原因
        """
        self._reset_daily_if_needed()
        strategy = signal.metadata.get("strategy_name", "unknown")

        if self._circuit_breaker_active.get(strategy, False):
            return False, f"Circuit breaker active for strategy '{strategy}'"

        notional = signal.price * signal.metadata.get("order_size", 0)
        if equity > 0 and notional / equity > self.max_position_pct:
            event = RiskEvent(
                event_type="position_limit",
                message=f"Position size {notional/equity:.1%} exceeds limit {self.max_position_pct:.1%}",
                timestamp=datetime.now(timezone.utc),
                strategy_name=strategy,
            )
            self._emit_event(event)
            return False, event.message

        if equity > 0 and current_position_value / equity > self.max_total_exposure_pct:
            return False, f"Total exposure {current_position_value/equity:.1%} exceeds limit {self.max_total_exposure_pct:.1%}"

        daily_loss = self._daily_pnl.get(strategy, 0)
        if equity > 0 and daily_loss < 0 and abs(daily_loss) / equity > self.max_daily_loss_pct:
            self._circuit_breaker_active[strategy] = True
            event = RiskEvent(
                event_type="circuit_breaker",
                message=f"Daily loss {abs(daily_loss)/equity:.1%} exceeds limit {self.max_daily_loss_pct:.1%}. Circuit breaker activated.",
                timestamp=datetime.now(timezone.utc),
                strategy_name=strategy,
                severity="critical",
            )
            self._emit_event(event)
            return False, event.message

        return True, "OK"

    def check_slippage(self, expected_price: float, actual_price: float) -> bool:
        """检查滑点是否在阈值内"""
        if expected_price == 0:
            return True
        slippage = abs(actual_price - expected_price) / expected_price
        if slippage > self.max_slippage_pct:
            event = RiskEvent(
                event_type="slippage_protection",
                message=f"Slippage {slippage:.2%} exceeds limit {self.max_slippage_pct:.2%}",
                timestamp=datetime.now(timezone.utc),
                severity="warning",
            )
            self._emit_event(event)
            return False
        return True

    def record_trade_result(self, strategy_name: str, pnl: float) -> None:
        """记录交易结果 - 更新日盈亏和连续亏损计数"""
        self._reset_daily_if_needed()
        self._daily_pnl[strategy_name] = self._daily_pnl.get(strategy_name, 0) + pnl

        if pnl < 0:
            self._consecutive_losses[strategy_name] = self._consecutive_losses.get(strategy_name, 0) + 1
            if self._consecutive_losses[strategy_name] >= self.consecutive_loss_limit:
                self._circuit_breaker_active[strategy_name] = True
                event = RiskEvent(
                    event_type="consecutive_loss_breaker",
                    message=f"Strategy '{strategy_name}' hit {self.consecutive_loss_limit} consecutive losses",
                    timestamp=datetime.now(timezone.utc),
                    strategy_name=strategy_name,
                    severity="critical",
                )
                self._emit_event(event)
        else:
            self._consecutive_losses[strategy_name] = 0

    def reset_circuit_breaker(self, strategy_name: str) -> None:
        self._circuit_breaker_active[strategy_name] = False

    def is_circuit_breaker_active(self, strategy_name: str) -> bool:
        return self._circuit_breaker_active.get(strategy_name, False)

    def get_risk_events(self) -> list[RiskEvent]:
        return list(self._risk_events)

    def get_status(self) -> dict[str, Any]:
        self._reset_daily_if_needed()
        return {
            "daily_pnl": dict(self._daily_pnl),
            "consecutive_losses": dict(self._consecutive_losses),
            "circuit_breakers": dict(self._circuit_breaker_active),
            "total_risk_events": len(self._risk_events),
        }
