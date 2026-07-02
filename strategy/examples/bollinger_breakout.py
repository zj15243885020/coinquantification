"""示例策略 - 布林带突破"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from strategy.base import Signal, SignalType, Strategy


class BollingerBreakoutStrategy(Strategy):
    """布林带突破策略 - 价格突破上轨做多，突破下轨做空"""

    def __init__(self, params: dict[str, Any] | None = None):
        default_params = {"period": 20, "std_dev": 2.0}
        merged = {**default_params, **(params or {})}
        super().__init__(name="bollinger_breakout", params=merged)
        self._prev_position: str | None = None

    def calculate_indicators(self, bars: pd.DataFrame, up_to: int) -> None:
        close = bars["close"].iloc[:up_to + 1]
        period = self.params["period"]
        std_dev = self.params["std_dev"]

        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        self.set_indicator("bb_middle", middle)
        self.set_indicator("bb_upper", middle + std_dev * std)
        self.set_indicator("bb_lower", middle - std_dev * std)

    def on_bar(self, bar_index: int, bars: pd.DataFrame) -> Signal | None:
        upper = self.get_indicator("bb_upper")
        lower = self.get_indicator("bb_lower")

        if upper is None or lower is None:
            self.calculate_indicators(bars, bar_index)
            upper = self.get_indicator("bb_upper")
            lower = self.get_indicator("bb_lower")

        if upper is None or lower is None:
            return None

        self.validate_bar_access(bar_index, bar_index)

        period = self.params["period"]
        if bar_index < period:
            return None

        price = float(bars["close"].iloc[bar_index])
        curr_upper = float(upper.iloc[bar_index])
        curr_lower = float(lower.iloc[bar_index])

        if np.isnan(curr_upper) or np.isnan(curr_lower):
            return None

        ts = bars["timestamp"].iloc[bar_index]
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()
        symbol = self.params.get("symbol", "BTC/USDT")

        signal = None

        if price > curr_upper and self._prev_position != "long":
            signal = Signal(
                signal_type=SignalType.LONG,
                symbol=symbol,
                timestamp=ts,
                price=price,
                strength=min((price - curr_upper) / curr_upper * 100, 1.0),
                metadata={"bb_upper": curr_upper, "bb_lower": curr_lower},
            )
            self._prev_position = "long"
        elif price < curr_lower and self._prev_position != "short":
            signal = Signal(
                signal_type=SignalType.SHORT,
                symbol=symbol,
                timestamp=ts,
                price=price,
                strength=min((curr_lower - price) / curr_lower * 100, 1.0),
                metadata={"bb_upper": curr_upper, "bb_lower": curr_lower},
            )
            self._prev_position = "short"

        return signal
