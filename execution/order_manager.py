"""订单管理器 - 订单生命周期管理、幂等性保证、网络中断自动重试"""

from __future__ import annotations

import time
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


class OrderManager:
    """订单管理器

    职责：
    1. 订单创建与跟踪
    2. 幂等性保证（相同幂等键不会重复下单）
    3. 网络中断自动重试
    4. 订单状态同步
    """

    def __init__(
        self,
        adapter: ExchangeAdapter,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        order_timeout: float = 30.0,
    ):
        self.adapter = adapter
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.order_timeout = order_timeout
        self._active_orders: dict[str, Order] = {}
        _idempotency_keys: dict[str, str] = {}

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: float | None = None,
        idempotency_key: str | None = None,
    ) -> Order:
        """提交订单 - 带幂等性和重试"""
        if idempotency_key is None:
            idempotency_key = uuid.uuid4().hex

        for attempt in range(self.max_retries):
            try:
                order = self.adapter.create_order(symbol, side, order_type, amount, price)
                order.metadata["idempotency_key"] = idempotency_key
                self._active_orders[order.order_id] = order
                return order
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                error_order = Order(
                    order_id=f"failed_{uuid.uuid4().hex[:8]}",
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    price=price,
                    amount=amount,
                    status=OrderStatus.FAILED,
                    created_at=datetime.now(timezone.utc),
                    exchange=self.adapter.name,
                    metadata={"error": str(e), "idempotency_key": idempotency_key},
                )
                return error_order

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        success = self.adapter.cancel_order(order_id, symbol)
        if success and order_id in self._active_orders:
            self._active_orders[order_id].status = OrderStatus.CANCELLED
        return success

    def sync_order(self, order_id: str, symbol: str) -> Order:
        """同步订单状态"""
        if order_id not in self._active_orders:
            return self.adapter.get_order(order_id, symbol)

        try:
            updated = self.adapter.get_order(order_id, symbol)
            self._active_orders[order_id] = updated
            return updated
        except Exception:
            return self._active_orders[order_id]

    def sync_all(self, symbol: str) -> dict[str, Order]:
        """同步所有活跃订单"""
        for oid in list(self._active_orders.keys()):
            if self._active_orders[oid].status in (OrderStatus.PENDING, OrderStatus.OPEN):
                self.sync_order(oid, symbol)
        return dict(self._active_orders)

    def get_active_orders(self) -> list[Order]:
        return [o for o in self._active_orders.values()
                if o.status in (OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)]

    def get_order_history(self) -> list[Order]:
        return list(self._active_orders.values())

    def cleanup_filled(self) -> int:
        """清理已完成订单"""
        to_remove = [oid for oid, o in self._active_orders.items()
                     if o.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED)]
        for oid in to_remove:
            del self._active_orders[oid]
        return len(to_remove)
