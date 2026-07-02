"""数据采集服务 - 统一的 OHLCV 数据获取接口"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd


class DataFeed:
    """统一数据采集接口 - 支持 Hyperliquid 和 Binance"""

    def __init__(self, exchange_adapter: Any):
        self._exchange = exchange_adapter

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: str | None = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """获取 K 线数据，返回标准 DataFrame 格式

        Returns:
            DataFrame with columns: [timestamp, open, high, low, close, volume]
            timestamp 为 UTC epoch ms
        """
        since_ms = None
        if since:
            since_ms = int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp() * 1000)

        raw = self._exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)

        if not raw:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def fetch_ohlcv_full(
        self,
        symbol: str,
        timeframe: str = "1h",
        start: str | None = None,
        end: str | None = None,
        batch_size: int = 500,
    ) -> pd.DataFrame:
        """分批获取完整 K 线数据"""
        all_data: list[pd.DataFrame] = []
        since_ms = None

        if start:
            since_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)

        end_ms = None
        if end:
            end_ms = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp() * 1000)

        while True:
            raw = self._exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=batch_size)
            if not raw:
                break

            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            all_data.append(df)

            last_ts = raw[-1][0]
            if end_ms and last_ts >= end_ms:
                break
            if len(raw) < batch_size:
                break

            since_ms = last_ts + 1
            time.sleep(0.1)

        if not all_data:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        result = pd.concat(all_data, ignore_index=True)
        result["timestamp"] = pd.to_datetime(result["timestamp"], unit="ms", utc=True)
        result = result.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        if end:
            end_dt = pd.Timestamp(end, tz="UTC")
            result = result[result["timestamp"] <= end_dt]

        return result

    def fetch_funding_rate(self, symbol: str) -> dict[str, Any] | None:
        """获取当前资金费率"""
        try:
            return self._exchange.fetch_funding_rate(symbol)
        except (AttributeError, NotImplementedError):
            return None
