"""本地时序存储 - SQLite 元数据 + Parquet 数据文件"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


class DataStore:
    """本地 K 线数据持久化 - 按交易对+时间框架分片存储为 parquet"""

    def __init__(self, cache_dir: str | Path = "./data_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._meta_db_path = self.cache_dir / "metadata.db"
        self._init_meta_db()

    def _init_meta_db(self) -> None:
        with sqlite3.connect(self._meta_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    start_ts TEXT NOT NULL,
                    end_ts TEXT NOT NULL,
                    bar_count INTEGER NOT NULL,
                    parquet_path TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timeframe, start_ts, end_ts)
                )
            """)

    def _parquet_path(self, symbol: str, timeframe: str) -> Path:
        safe_symbol = symbol.replace("/", "_").replace(":", "_")
        subdir = self.cache_dir / safe_symbol / timeframe
        subdir.mkdir(parents=True, exist_ok=True)
        return subdir / "data.parquet"

    def save_ohlcv(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Path:
        """保存 OHLCV 数据到 parquet，并记录元数据"""
        if df.empty:
            raise ValueError("Cannot save empty DataFrame")

        pq_path = self._parquet_path(symbol, timeframe)

        existing = pd.DataFrame()
        if pq_path.exists():
            existing = pd.read_parquet(pq_path)
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        else:
            combined = df.sort_values("timestamp").reset_index(drop=True)

        combined.to_parquet(pq_path, index=False)

        start_ts = str(combined["timestamp"].iloc[0])
        end_ts = str(combined["timestamp"].iloc[-1])
        bar_count = len(combined)

        with sqlite3.connect(self._meta_db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO ohlcv_meta
                   (symbol, timeframe, start_ts, end_ts, bar_count, parquet_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (symbol, timeframe, start_ts, end_ts, bar_count, str(pq_path)),
            )

        return pq_path

    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """加载 OHLCV 数据"""
        pq_path = self._parquet_path(symbol, timeframe)
        if not pq_path.exists():
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.read_parquet(pq_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        if start:
            start_dt = pd.Timestamp(start, tz="UTC")
            df = df[df["timestamp"] >= start_dt]
        if end:
            end_dt = pd.Timestamp(end, tz="UTC")
            df = df[df["timestamp"] <= end_dt]

        return df.sort_values("timestamp").reset_index(drop=True)

    def get_meta(self, symbol: str, timeframe: str) -> list[dict]:
        """查询元数据"""
        with sqlite3.connect(self._meta_db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ohlcv_meta WHERE symbol=? AND timeframe=? ORDER BY created_at DESC",
                (symbol, timeframe),
            ).fetchall()
            return [dict(r) for r in rows]

    def has_data(self, symbol: str, timeframe: str) -> bool:
        """检查是否有缓存数据"""
        pq_path = self._parquet_path(symbol, timeframe)
        return pq_path.exists()
