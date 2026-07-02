"""示例策略 - 双均线交叉"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from strategy.base import Signal, SignalType, Strategy


class DualMAStrategy(Strategy):
    """双均线交叉策略 - 快线上穿慢线做多，下穿做空"""

    def __init__(self, params: dict[str, Any] | None = None):
        default_params = {"fast_period": 10, "slow_period": 30}
        merged = {**default_params, **(params or {})}
        super().__init__(name="dual_ma", params=merged)
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def calculate_indicators(self, bars: pd.DataFrame, up_to: int) -> None:
        close = bars["close"].iloc[:up_to + 1]
        fast_period = self.params["fast_period"]
        slow_period = self.params["slow_period"]

        self.set_indicator("fast_ma", close.rolling(window=fast_period).mean())
        self.set_indicator("slow_ma", close.rolling(window=slow_period).mean())

    def on_bar(self, bar_index: int, bars: pd.DataFrame) -> Signal | None:
        fast_ma = self.get_indicator("fast_ma")
        slow_ma = self.get_indicator("slow_ma")

        if fast_ma is None or slow_ma is None:
            self.calculate_indicators(bars, bar_index)
            fast_ma = self.get_indicator("fast_ma")
            slow_ma = self.get_indicator("slow_ma")

        if fast_ma is None or slow_ma is None:
            return None

        self.validate_bar_access(bar_index, bar_index)

        fast_period = self.params["fast_period"]
        slow_period = self.params["slow_period"]
        if bar_index < slow_period:
            return None

        curr_fast = fast_ma.iloc[bar_index]
        curr_slow = slow_ma.iloc[bar_index]

        if pd.isna(curr_fast) or pd.isna(curr_slow):
            return None

        ts = bars["timestamp"].iloc[bar_index]
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()
        price = float(bars["close"].iloc[bar_index])
        symbol = self.params.get("symbol", "BTC/USDT")

        signal = None

        if self._prev_fast is not None and self._prev_slow is not None:
            if self._prev_fast <= self._prev_slow and curr_fast > curr_slow:
                signal = Signal(
                    signal_type=SignalType.LONG,
                    symbol=symbol,
                    timestamp=ts,
                    price=price,
                    strength=min(abs(curr_fast - curr_slow) / curr_slow * 100, 1.0),
                    metadata={"fast_ma": curr_fast, "slow_ma": curr_slow},
                )
            elif self._prev_fast >= self._prev_slow and curr_fast < curr_slow:
                signal = Signal(
                    signal_type=SignalType.SHORT,
                    symbol=symbol,
                    timestamp=ts,
                    price=price,
                    strength=min(abs(curr_fast - curr_slow) / curr_slow * 100, 1.0),
                    metadata={"fast_ma": curr_fast, "slow_ma": curr_slow},
                )

        self._prev_fast = curr_fast
        self._prev_slow = curr_slow

        return signal
