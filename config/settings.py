"""配置系统 - YAML 配置加载 + pydantic 校验 + 环境变量覆盖"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class CommissionConfig(BaseModel):
    maker: float = 0.0002
    taker: float = 0.0005


class SlippageConfig(BaseModel):
    model: str = "fixed"
    value: float = 0.0001


class ExchangeOptionsConfig(BaseModel):
    default_type: str = Field(default="future", alias="defaultType")

    model_config = {"populate_by_name": True}


class ExchangeConfig(BaseModel):
    enabled: bool = False
    type: str = "futures"
    testnet: bool = True
    mainnet: bool = False
    options: ExchangeOptionsConfig | None = None


class DataConfig(BaseModel):
    cache_dir: str = "./data_cache"
    default_timeframes: list[str] = Field(default_factory=lambda: ["1h", "4h", "1d"])
    default_symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])


class BacktestConfig(BaseModel):
    initial_capital: float = 10000.0
    commission: CommissionConfig = Field(default_factory=CommissionConfig)
    slippage: SlippageConfig = Field(default_factory=SlippageConfig)
    start_date: str = "2025-01-01"
    end_date: str = "2026-07-01"


class CircuitBreakerConfig(BaseModel):
    enabled: bool = True
    consecutive_losses: int = 5


class RiskConfig(BaseModel):
    max_position_pct: float = 0.1
    max_daily_loss_pct: float = 0.05
    max_total_exposure_pct: float = 0.5
    max_slippage_pct: float = 0.005
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)


class TelegramAlertConfig(BaseModel):
    enabled: bool = False


class MonitoringConfig(BaseModel):
    telegram: TelegramAlertConfig = Field(default_factory=TelegramAlertConfig)
    alert_events: list[str] = Field(default_factory=lambda: [
        "circuit_breaker", "large_loss", "connection_lost", "order_filled"
    ])


class SystemConfig(BaseModel):
    name: str = "crypto-quant-mvp"
    mode: str = "backtest"
    log_level: str = "INFO"
    log_format: str = "json"


class Settings(BaseSettings):
    system: SystemConfig = Field(default_factory=SystemConfig)
    exchanges: dict[str, ExchangeConfig] = Field(default_factory=dict)
    data: DataConfig = Field(default_factory=DataConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    strategies: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = {"env_prefix": "CQUANT_", "populate_by_name": True}


def load_settings(config_path: str | Path | None = None) -> Settings:
    """加载 YAML 配置文件并合并环境变量覆盖"""
    yaml_data: dict[str, Any] = {}

    if config_path is None:
        config_path = Path(__file__).parent / "settings.yaml"

    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    env_override = os.environ.get("CQUANT_CONFIG")
    if env_override:
        env_path = Path(env_override)
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}

    return Settings(**yaml_data)
