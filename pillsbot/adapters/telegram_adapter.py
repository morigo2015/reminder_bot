from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Awaitable, Any

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import ChatMemberUpdatedFilter

class TelegramAdapter:
    """Thin wrapper around aiogram to integrate with ReminderEngine."""

    def __init__(self, bot_token: str, engine: Any, patient_groups: list[int]):
        self.bot = Bot(token=bot_token, parse_mode=None)
        self.dp = Dispatcher()
        self.engine = engine
        self.patient_groups = set(patient_groups)

        @self.dp.message(F.chat.id.in_(self.patient_groups) & F.text)
        async def on_group_text(msg: Message):
            # Only raw patient text is forwarded; engine will re-check sender id
            incoming = engine.IncomingMessage(
                group_id=msg.chat.id,
                sender_user_id=msg.from_user.id if msg.from_user else 0,
                text=msg.text or "",
                sent_at_utc=datetime.now(timezone.utc),
            )
            await self.engine.on_patient_message(incoming)

    async def send_group_message(self, group_id: int, text: str) -> None:
        await self.bot.send_message(chat_id=group_id, text=text)

    async def send_nurse_dm(self, user_id: int, text: str) -> None:
        await self.bot.send_message(chat_id=user_id, text=text)

    async def run_polling(self) -> None:
        await self.dp.start_polling(self.bot)

# expose IncomingMessage for adapter
from pillsbot.core.reminder_engine import IncomingMessage  # noqa: E402
__all__ = ["TelegramAdapter", "IncomingMessage"]
