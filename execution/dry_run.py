"""模拟盘模式 - 基于实时行情的纸上交易"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from execution.adapters.base import (
    ExchangeAdapter,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)


class DryRunAdapter(ExchangeAdapter):
    """模拟盘适配器 - 不发送真实订单，本地模拟撮合"""

    def __init__(self, underlying: ExchangeAdapter, config: dict[str, Any] | None = None):
        super().__init__(name=f"dry_run_{underlying.name}", config=config)
        self._underlying = underlying
        self._orders: dict[str, Order] = {}
        self._balance: dict[str, float] = {"USDT": 10000.0}
        self._positions: dict[str, dict[str, Any]] = {}
        self._commission_rate = (config or {}).get("commission_rate", 0.0005)

    def connect(self, api_key: str = "", secret: str = "", **kwargs) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", since: int | None = None, limit: int = 500
    ) -> list[list[float]]:
        return self._underlying.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)

    def create_order(
        self, symbol: str, side: OrderSide, order_type: OrderType,
        amount: float, price: float | None = None
    ) -> Order:
        ticker = self._underlying.fetch_ticker(symbol)
        exec_price = price if price else ticker["last"]

        if order_type == OrderType.MARKET:
            slippage = exec_price * 0.0001
            exec_price = exec_price + slippage if side == OrderSide.BUY else exec_price - slippage

        commission = exec_price * amount * self._commission_rate
        order_id = f"dry_{uuid.uuid4().hex[:12]}"

        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=exec_price,
            amount=amount,
            filled_amount=amount,
            filled_price=exec_price,
            status=OrderStatus.FILLED,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            exchange=f"dry_run_{self._underlying.name}",
            metadata={"commission": commission, "dry_run": True},
        )

        self._orders[order_id] = order
        self._update_position(symbol, side, amount, exec_price)
        return order

    def _update_position(self, symbol: str, side: OrderSide, amount: float, price: float) -> None:
        if symbol not in self._positions:
            self._positions[symbol] = {"side": side.value, "size": 0.0, "entry_price": 0.0}

        pos = self._positions[symbol]
        if side == OrderSide.BUY:
            pos["size"] += amount
            if pos["size"] > 0:
                pos["entry_price"] = price
        else:
            pos["size"] -= amount
            if pos["size"] < 0:
                pos["side"] = "short"
                pos["size"] = abs(pos["size"])
                pos["entry_price"] = price
            elif pos["size"] == 0:
                pos["side"] = "none"

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        if order_id in self._orders:
            self._orders[order_id].status = OrderStatus.CANCELLED
            return True
        return False

    def get_order(self, order_id: str, symbol: str) -> Order:
        if order_id in self._orders:
            return self._orders[order_id]
        raise ValueError(f"Order not found: {order_id}")

    def get_balance(self) -> dict[str, float]:
        return dict(self._balance)

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        pos = self._positions.get(symbol)
        if not pos or pos["size"] == 0:
            return None
        return pos

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        return self._underlying.fetch_ticker(symbol)

    def get_order_history(self) -> list[Order]:
        return list(self._orders.values())
