"""Hyperliquid 永续 DEX 适配器 - 基于官方 Python SDK"""

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


class HyperliquidAdapter(ExchangeAdapter):
    """Hyperliquid 永续合约适配器"""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(name="hyperliquid", config=config)
        self._info = None
        self._exchange_client = None

    def connect(self, api_key: str = "", secret: str = "", **kwargs) -> None:
        """连接 Hyperliquid

        Args:
            secret: Hyperliquid 钱包私钥（用于签名交易）
            api_key: 可选的 API key（用于只读查询）
        """
        from hyperliquid.info import Info
        from hyperliquid.exchange import Exchange

        mainnet = self.config.get("mainnet", False)
        base_url = "https://api.hyperliquid.xyz" if mainnet else "https://api.hyperliquid-testnet.xyz"

        self._info = Info(base_url, skip_ws=False)

        if secret:
            wallet_address = kwargs.get("wallet_address", "")
            self._exchange_client = Exchange(
                secret=secret,
                base_url=base_url,
                account_address=wallet_address if wallet_address else None,
            )

        self._connected = True

    def disconnect(self) -> None:
        self._info = None
        self._exchange_client = None
        self._connected = False

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", since: int | None = None, limit: int = 500
    ) -> list[list[float]]:
        if not self._info:
            raise RuntimeError("Not connected.")

        tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        interval = tf_map.get(timeframe, "1h")

        coin = symbol.split("/")[0]
        candles = self._info.candles_snapshot(coin, interval, since or 0)

        result = []
        for c in candles[-limit:]:
            result.append([
                c["t"],
                float(c["o"]),
                float(c["h"]),
                float(c["l"]),
                float(c["c"]),
                float(c.get("v", 0)),
            ])
        return result

    def create_order(
        self, symbol: str, side: OrderSide, order_type: OrderType,
        amount: float, price: float | None = None
    ) -> Order:
        if not self._exchange_client:
            raise RuntimeError("Not connected with private key.")

        coin = symbol.split("/")[0]
        is_buy = side == OrderSide.BUY

        if order_type == OrderType.LIMIT and price is not None:
            order_result = self._exchange_client.order(
                coin=coin,
                is_buy=is_buy,
                sz=amount,
                limit_px=price,
                order_type={"limit": {"tif": "Gtc"}},
            )
        else:
            ticker = self.fetch_ticker(symbol)
            slippage_price = ticker["last"] * (1.005 if is_buy else 0.995)
            order_result = self._exchange_client.order(
                coin=coin,
                is_buy=is_buy,
                sz=amount,
                limit_px=slippage_price,
                order_type={"limit": {"tif": "Ioc"}},
            )

        order_id = str(uuid.uuid4().hex[:16])
        if isinstance(order_result, dict) and "response" in order_result:
            resp = order_result.get("response", {})
            data = resp.get("data", {})
            statuses = data.get("statuses", [])
            if statuses:
                order_id = str(statuses[0].get("oid", order_id))

        return Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            amount=amount,
            status=OrderStatus.OPEN,
            created_at=datetime.now(timezone.utc),
            exchange="hyperliquid",
        )

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        if not self._exchange_client:
            raise RuntimeError("Not connected with private key.")
        try:
            coin = symbol.split("/")[0]
            self._exchange_client.cancel(coin=coin, oid=int(order_id))
            return True
        except Exception:
            return False

    def get_order(self, order_id: str, symbol: str) -> Order:
        return Order(
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.FILLED,
            exchange="hyperliquid",
        )

    def get_balance(self) -> dict[str, float]:
        if not self._info:
            raise RuntimeError("Not connected.")
        wallet = self.config.get("wallet_address", "")
        if not wallet:
            return {}
        state = self._info.user_state(wallet)
        balance = float(state.get("marginSummary", {}).get("accountValue", 0))
        return {"USDT": balance} if balance > 0 else {}

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        if not self._info:
            raise RuntimeError("Not connected.")
        wallet = self.config.get("wallet_address", "")
        if not wallet:
            return None
        state = self._info.user_state(wallet)
        positions = state.get("assetPositions", [])
        coin = symbol.split("/")[0]
        for pos in positions:
            position = pos.get("position", {})
            if position.get("coin") == coin:
                size = float(position.get("szi", 0))
                if size == 0:
                    return None
                return {
                    "symbol": symbol,
                    "side": "long" if size > 0 else "short",
                    "size": abs(size),
                    "entry_price": float(position.get("entryPx", 0)),
                    "unrealized_pnl": float(position.get("unrealizedPnl", 0)),
                }
        return None

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        if not self._info:
            raise RuntimeError("Not connected.")
        coin = symbol.split("/")[0]
        meta = self._info.meta()
        all_mids = self._info.all_mids()
        price = float(all_mids.get(coin, 0))
        return {
            "symbol": symbol,
            "last": price,
            "bid": price,
            "ask": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
