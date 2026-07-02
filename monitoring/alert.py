"""Telegram 告警通知"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from risk.engine import RiskEvent

logger = logging.getLogger("cquant.alert")


class TelegramAlert:
    """Telegram Bot 告警通知"""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """发送消息"""
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_risk_event(self, event: RiskEvent) -> bool:
        """发送风控事件告警"""
        severity_emoji = {"warning": "⚠️", "critical": "🚨"}.get(event.severity, "ℹ️")
        text = (
            f"{severity_emoji} <b>风控告警</b>\n\n"
            f"<b>类型:</b> {event.event_type}\n"
            f"<b>策略:</b> {event.strategy_name or 'N/A'}\n"
            f"<b>级别:</b> {event.severity}\n"
            f"<b>详情:</b> {event.message}\n"
            f"<b>时间:</b> {event.timestamp.isoformat()}"
        )
        return await self.send_message(text)

    async def send_trade_notification(
        self,
        symbol: str,
        side: str,
        price: float,
        amount: float,
        strategy: str = "",
    ) -> bool:
        """发送交易通知"""
        emoji = "🟢" if side == "buy" else "🔴"
        text = (
            f"{emoji} <b>交易通知</b>\n\n"
            f"<b>交易对:</b> {symbol}\n"
            f"<b>方向:</b> {side.upper()}\n"
            f"<b>价格:</b> ${price:,.2f}\n"
            f"<b>数量:</b> {amount}\n"
            f"<b>策略:</b> {strategy or 'N/A'}"
        )
        return await self.send_message(text)

    def on_risk_event(self, event: RiskEvent) -> None:
        """同步回调 - 用于 RiskEngine.on_alert()"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.send_risk_event(event))
        except RuntimeError:
            asyncio.run(self.send_risk_event(event))
