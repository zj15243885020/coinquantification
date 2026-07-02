"""资金隔离 - 每个策略实例独立资金池"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyAllocation:
    """策略资金分配"""
    strategy_name: str
    allocated_capital: float = 0.0
    used_capital: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    open_positions: int = 0

    @property
    def available_capital(self) -> float:
        return max(0, self.allocated_capital - self.used_capital)

    @property
    def total_equity(self) -> float:
        return self.allocated_capital + self.realized_pnl + self.unrealized_pnl


class AllocationManager:
    """资金隔离管理器 - 每个策略独立资金池，互不影响"""

    def __init__(self, total_capital: float):
        self.total_capital = total_capital
        self._allocations: dict[str, StrategyAllocation] = {}

    def allocate(self, strategy_name: str, capital: float) -> StrategyAllocation:
        """为策略分配资金"""
        if capital > self.available_capital:
            raise ValueError(
                f"Insufficient capital. Requested: {capital}, Available: {self.available_capital}"
            )

        if strategy_name in self._allocations:
            self._allocations[strategy_name].allocated_capital += capital
        else:
            self._allocations[strategy_name] = StrategyAllocation(
                strategy_name=strategy_name,
                allocated_capital=capital,
            )
        return self._allocations[strategy_name]

    @property
    def available_capital(self) -> float:
        used = sum(a.allocated_capital for a in self._allocations.values())
        return self.total_capital - used

    def get_allocation(self, strategy_name: str) -> StrategyAllocation | None:
        return self._allocations.get(strategy_name)

    def update_pnl(self, strategy_name: str, realized: float = 0, unrealized: float = 0) -> None:
        alloc = self._allocations.get(strategy_name)
        if alloc:
            alloc.realized_pnl += realized
            alloc.unrealized_pnl += unrealized

    def update_position(self, strategy_name: str, used_delta: float, position_delta: int = 0) -> None:
        alloc = self._allocations.get(strategy_name)
        if alloc:
            alloc.used_capital += used_delta
            alloc.open_positions += position_delta

    def get_all_allocations(self) -> dict[str, StrategyAllocation]:
        return dict(self._allocations)

    def get_summary(self) -> dict[str, Any]:
        return {
            "total_capital": self.total_capital,
            "available_capital": self.available_capital,
            "allocations": {
                name: {
                    "allocated": a.allocated_capital,
                    "used": a.used_capital,
                    "available": a.available_capital,
                    "realized_pnl": a.realized_pnl,
                    "unrealized_pnl": a.unrealized_pnl,
                    "open_positions": a.open_positions,
                }
                for name, a in self._allocations.items()
            },
        }
