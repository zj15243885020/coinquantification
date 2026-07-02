from strategy.base import Signal, SignalType, Strategy
from strategy.examples.dual_ma import DualMAStrategy
from strategy.examples.bollinger_breakout import BollingerBreakoutStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "dual_ma": DualMAStrategy,
    "bollinger_breakout": BollingerBreakoutStrategy,
}

__all__ = [
    "Signal",
    "SignalType",
    "Strategy",
    "DualMAStrategy",
    "BollingerBreakoutStrategy",
    "STRATEGY_REGISTRY",
]
