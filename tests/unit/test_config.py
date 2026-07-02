"""单元测试 - 配置系统"""

from pathlib import Path
import tempfile
import pytest

from config.settings import load_settings, Settings


class TestSettings:
    def test_load_default_settings(self):
        settings = Settings()
        assert settings.system.name == "crypto-quant-mvp"
        assert settings.system.mode == "backtest"
        assert settings.backtest.initial_capital == 10000.0

    def test_load_from_yaml(self, tmp_path):
        config_content = """
system:
  name: "test-system"
  mode: "live"
backtest:
  initial_capital: 5000.0
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(config_content)

        settings = load_settings(config_file)
        assert settings.system.name == "test-system"
        assert settings.system.mode == "live"
        assert settings.backtest.initial_capital == 5000.0

    def test_risk_config_defaults(self):
        settings = Settings()
        assert settings.risk.max_position_pct == 0.1
        assert settings.risk.max_daily_loss_pct == 0.05
        assert settings.risk.circuit_breaker.enabled is True
