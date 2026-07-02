"""策略引擎 - 策略基类与信号数据结构"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd


class SignalType(str, Enum):
    LONG = "long"
    SHORT = "short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    HOLD = "hold"


@dataclass
class Signal:
    """策略信号"""
    signal_type: SignalType
    symbol: str
    timestamp: datetime
    price: float
    strength: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_entry(self) -> bool:
        return self.signal_type in (SignalType.LONG, SignalType.SHORT)

    @property
    def is_exit(self) -> bool:
        return self.signal_type in (SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT)


class Strategy(ABC):
    """策略抽象基类 - 所有策略必须继承此类"""

    def __init__(self, name: str, params: dict[str, Any] | None = None):
        self.name = name
        self.params = params or {}
        self._indicators: dict[str, pd.Series] = {}

    @abstractmethod
    def on_bar(self, bar_index: int, bars: pd.DataFrame) -> Signal | None:
        """每根 K 线闭合时调用 - 核心策略逻辑

        Args:
            bar_index: 当前 bar 索引（只能访问 bars[0..bar_index]）
            bars: 完整 K 线 DataFrame，包含 timestamp/open/high/low/close/volume

        Returns:
            Signal 或 None（无信号时返回 None）
        """

    def on_tick(self, tick: dict[str, Any]) -> Signal | None:
        """实时 tick 数据回调（可选实现，回测模式不使用）"""
        return None

    def calculate_indicators(self, bars: pd.DataFrame, up_to: int) -> None:
        """预计算指标 - 在 on_bar 之前调用

        Args:
            bars: 完整 K 线数据
            up_to: 计算到第几根 bar（含）
        """

    def get_indicator(self, name: str) -> pd.Series | None:
        return self._indicators.get(name)

    def set_indicator(self, name: str, series: pd.Series) -> None:
        self._indicators[name] = series

    def validate_bar_access(self, bar_index: int, accessed_index: int) -> None:
        """前瞻偏差防护 - 确保只访问当前及历史数据

        Raises:
            ValueError: 如果尝试访问未来数据
        """
        if accessed_index > bar_index:
            raise ValueError(
                f"Look-ahead bias detected! "
                f"Strategy '{self.name}' at bar {bar_index} tried to access bar {accessed_index}. "
                f"Only bars [0..{bar_index}] are accessible."
            )
