# pillsbot/adapters/telegram_adapter.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

from pillsbot.core.reminder_engine import IncomingMessage
from pillsbot.core.logging_utils import kv


class TelegramAdapter:
    """Thin wrapper around aiogram to integrate with ReminderEngine."""

    def __init__(
        self, bot_token: str, engine: Any, patient_groups: Iterable[int]
    ) -> None:
        self.bot = Bot(token=bot_token, parse_mode=None)
        self.dp = Dispatcher()

        self.engine = engine
        self.patient_groups = set(patient_groups)

        self.log = logging.getLogger("pillsbot.adapter")

        self.dp.message.register(self.on_group_text, F.text)

    async def on_group_text(self, message: Message) -> None:
        """Handle text messages in patient group chats and forward to the engine."""
        chat_id = message.chat.id
        text = message.text or ""
        sender_user_id = message.from_user.id if message.from_user else 0

        # Always log inbound traffic (messaging stays INFO)
        self.log.info(
            "msg.in.group "
            + kv(group_id=chat_id, sender_user_id=sender_user_id, text=text)
        )

        if chat_id not in self.patient_groups:
            self.log.debug("msg.in.ignored " + kv(reason="not a patient group"))
            return

        incoming = IncomingMessage(
            group_id=chat_id,
            sender_user_id=sender_user_id,
            text=text,
            sent_at_utc=datetime.now(timezone.utc),
        )

        await self.engine.on_patient_message(incoming)

    async def send_group_message(self, group_id: int, text: str) -> None:
        # Messaging → INFO
        self.log.info("msg.out.group " + kv(group_id=group_id, text=text))
        await self.bot.send_message(chat_id=group_id, text=text)

    async def send_nurse_dm(self, user_id: int, text: str) -> None:
        # Messaging → INFO
        self.log.info("msg.out.dm " + kv(user_id=user_id, text=text))
        await self.bot.send_message(chat_id=user_id, text=text)

    async def run_polling(self) -> None:
        self.log.debug("polling.run")
        await self.dp.start_polling(self.bot)


__all__ = ["TelegramAdapter", "IncomingMessage"]
