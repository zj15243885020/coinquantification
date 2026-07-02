"""单元测试 - 数据存储"""

import pandas as pd
import pytest
import numpy as np

from data.store.data_store import DataStore


class TestDataStore:
    def test_save_and_load(self, tmp_path):
        store = DataStore(cache_dir=tmp_path)
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=100, freq="1h", tz="UTC"),
            "open": np.random.uniform(40000, 50000, 100),
            "high": np.random.uniform(50000, 55000, 100),
            "low": np.random.uniform(35000, 40000, 100),
            "close": np.random.uniform(40000, 50000, 100),
            "volume": np.random.uniform(100, 1000, 100),
        })

        store.save_ohlcv("BTC/USDT", "1h", df)
        loaded = store.load_ohlcv("BTC/USDT", "1h")

        assert len(loaded) == 100
        assert "timestamp" in loaded.columns
        assert "close" in loaded.columns

    def test_load_nonexistent_returns_empty(self, tmp_path):
        store = DataStore(cache_dir=tmp_path)
        result = store.load_ohlcv("NONEXIST/USDT", "1h")
        assert result.empty

    def test_has_data(self, tmp_path):
        store = DataStore(cache_dir=tmp_path)
        assert store.has_data("BTC/USDT", "1h") is False

        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=10, freq="1h", tz="UTC"),
            "open": [1.0] * 10, "high": [2.0] * 10, "low": [0.5] * 10,
            "close": [1.5] * 10, "volume": [100.0] * 10,
        })
        store.save_ohlcv("BTC/USDT", "1h", df)
        assert store.has_data("BTC/USDT", "1h") is True

    def test_save_empty_raises(self, tmp_path):
        store = DataStore(cache_dir=tmp_path)
        with pytest.raises(ValueError, match="empty"):
            store.save_ohlcv("BTC/USDT", "1h", pd.DataFrame())
