"""Binance 合约适配器 - 基于 ccxt"""

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


class BinanceAdapter(ExchangeAdapter):
    """Binance U 本位合约适配器"""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(name="binance", config=config)
        self._exchange = None

    def connect(self, api_key: str = "", secret: str = "", **kwargs) -> None:
        import ccxt

        options = self.config.get("options", {})
        testnet = self.config.get("testnet", True)

        self._exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": secret,
            "options": {**options, "defaultType": "future"},
            "enableRateLimit": True,
        })

        if testnet:
            self._exchange.set_sandbox_mode(True)

        self._exchange.load_markets()
        self._connected = True

    def disconnect(self) -> None:
        self._exchange = None
        self._connected = False

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", since: int | None = None, limit: int = 500
    ) -> list[list[float]]:
        if not self._exchange:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)

    def create_order(
        self, symbol: str, side: OrderSide, order_type: OrderType,
        amount: float, price: float | None = None
    ) -> Order:
        if not self._exchange:
            raise RuntimeError("Not connected. Call connect() first.")

        ccxt_type = "market" if order_type == OrderType.MARKET else "limit"
        raw = self._exchange.create_order(symbol, ccxt_type, side.value, amount, price)

        return Order(
            order_id=str(raw.get("id", uuid.uuid4().hex)),
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            amount=amount,
            filled_amount=float(raw.get("filled", 0) or 0),
            filled_price=float(raw.get("average", 0) or 0) if raw.get("average") else None,
            status=self._map_status(raw.get("status", "")),
            created_at=datetime.fromtimestamp(raw["timestamp"] / 1000, tz=timezone.utc) if raw.get("timestamp") else datetime.now(timezone.utc),
            exchange="binance",
        )

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        if not self._exchange:
            raise RuntimeError("Not connected.")
        try:
            self._exchange.cancel_order(order_id, symbol)
            return True
        except Exception:
            return False

    def get_order(self, order_id: str, symbol: str) -> Order:
        if not self._exchange:
            raise RuntimeError("Not connected.")
        raw = self._exchange.fetch_order(order_id, symbol)
        return Order(
            order_id=str(raw["id"]),
            symbol=raw.get("symbol", symbol),
            side=OrderSide(raw["side"]),
            order_type=OrderType(raw["type"]),
            price=float(raw.get("price", 0) or 0),
            amount=float(raw.get("amount", 0)),
            filled_amount=float(raw.get("filled", 0) or 0),
            filled_price=float(raw.get("average", 0) or 0) if raw.get("average") else None,
            status=self._map_status(raw.get("status", "")),
            exchange="binance",
        )

    def get_balance(self) -> dict[str, float]:
        if not self._exchange:
            raise RuntimeError("Not connected.")
        balance = self._exchange.fetch_balance()
        return {k: float(v.get("free", 0)) for k, v in balance.get("total", {}).items() if float(v.get("free", 0)) > 0}

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        if not self._exchange:
            raise RuntimeError("Not connected.")
        try:
            positions = self._exchange.fetch_positions([symbol])
            for pos in positions:
                if pos.get("symbol") == symbol and float(pos.get("contracts", 0)) > 0:
                    return {
                        "symbol": symbol,
                        "side": pos.get("side"),
                        "size": float(pos.get("contracts", 0)),
                        "entry_price": float(pos.get("entryPrice", 0)),
                        "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                    }
        except Exception:
            pass
        return None

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        if not self._exchange:
            raise RuntimeError("Not connected.")
        return self._exchange.fetch_ticker(symbol)

    def fetch_funding_rate(self, symbol: str) -> dict[str, Any] | None:
        if not self._exchange:
            raise RuntimeError("Not connected.")
        try:
            return self._exchange.fetch_funding_rate(symbol)
        except Exception:
            return None

    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "rejected": OrderStatus.FAILED,
        }
        return mapping.get(status.lower(), OrderStatus.PENDING)
