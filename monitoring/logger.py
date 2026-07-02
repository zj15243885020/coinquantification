"""结构化日志系统 - JSON 格式，密钥脱敏"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SensitiveDataFilter(logging.Filter):
    """日志脱敏过滤器 - 移除日志中的密钥信息"""

    SENSITIVE_PATTERNS = [
        "api_key", "api_secret", "secret", "private_key", "password", "token",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern in msg.lower():
                record.msg = f"[REDACTED] Message contained sensitive pattern: {pattern}"
                record.args = ()
        return True


class JSONFormatter(logging.Formatter):
    """JSON 格式日志"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data
        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """控制台友好格式"""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        msg = record.getMessage()
        return f"{ts} [{record.levelname:>8}] {record.name}: {msg}"


def setup_logger(
    name: str = "cquant",
    level: str = "INFO",
    log_format: str = "json",
    log_dir: str = "./logs",
) -> logging.Logger:
    """配置日志系统"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.addFilter(SensitiveDataFilter())

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    console_handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path / "cquant.log", encoding="utf-8")
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "cquant") -> logging.Logger:
    return logging.getLogger(name)
