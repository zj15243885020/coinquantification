"""交易所适配器抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Order:
    """统一订单结构"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: float | None = None
    amount: float = 0.0
    filled_amount: float = 0.0
    filled_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime | None = None
    updated_at: datetime | None = None
    exchange: str = ""
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ExchangeAdapter(ABC):
    """交易所适配器抽象基类"""

    def __init__(self, name: str, config: dict[str, Any] | None = None):
        self.name = name
        self.config = config or {}
        self._connected = False

    @abstractmethod
    def connect(self, api_key: str = "", secret: str = "", **kwargs) -> None:
        """连接交易所"""

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""

    @abstractmethod
    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", since: int | None = None, limit: int = 500
    ) -> list[list[float]]:
        """获取 K 线数据"""

    @abstractmethod
    def create_order(
        self, symbol: str, side: OrderSide, order_type: OrderType,
        amount: float, price: float | None = None
    ) -> Order:
        """创建订单"""

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""

    @abstractmethod
    def get_order(self, order_id: str, symbol: str) -> Order:
        """查询订单状态"""

    @abstractmethod
    def get_balance(self) -> dict[str, float]:
        """查询余额"""

    @abstractmethod
    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """查询仓位"""

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """获取最新行情"""

    @property
    def is_connected(self) -> bool:
        return self._connected
