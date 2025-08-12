# pillsbot/adapters/telegram_adapter.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)

from pillsbot.core.reminder_engine import IncomingMessage, DoseKey
from pillsbot.core.logging_utils import kv
from pillsbot.core.i18n import MESSAGES


class TelegramAdapter:
    """Thin wrapper around aiogram to integrate with ReminderEngine, plus v3 UI helpers."""

    def __init__(
        self, bot_token: str, engine: Any, patient_groups: Iterable[int]
    ) -> None:
        self.bot = Bot(token=bot_token, parse_mode=None)
        self.dp = Dispatcher()

        self.engine = engine
        self.patient_groups = set(patient_groups)

        self.log = logging.getLogger("pillsbot.adapter")

        # Text in groups
        self.dp.message.register(self.on_group_text, F.text)
        # Inline button callbacks (v3)
        self.dp.callback_query.register(
            self.on_callback_confirm, F.data.startswith("confirm:")
        )

    # ------------------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------------------
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

    async def on_callback_confirm(self, callback: CallbackQuery) -> None:
        """
        Handle inline confirmation button presses.
        Passes through to engine for validation & state mutation,
        then answers the callback (ephemeral).
        """
        try:
            group_id = callback.message.chat.id if callback.message else 0
        except Exception:
            group_id = 0
        from_user_id = callback.from_user.id if callback.from_user else 0
        data = callback.data or ""
        message_id = callback.message.message_id if callback.message else None

        # Engine decides the outcome and any ephemeral text to show
        result: dict[str, Any] = await self.engine.on_inline_confirm(
            group_id=group_id,
            from_user_id=from_user_id,
            data=data,
            message_id=message_id,
        )
        cb_text: Optional[str] = result.get("cb_text")
        show_alert: bool = bool(result.get("show_alert", False))

        await self.answer_callback(callback.id, text=cb_text, show_alert=show_alert)

    # ------------------------------------------------------------------------------
    # Outbound messaging
    # ------------------------------------------------------------------------------
    async def send_group_message(
        self, group_id: int, text: str, reply_markup: Any | None = None
    ) -> int:
        """
        Sends a group message and returns Telegram message_id.
        Messaging-level logging remains at INFO.
        """
        self.log.info("msg.out.group " + kv(group_id=group_id, text=text))
        msg = await self.bot.send_message(
            chat_id=group_id, text=text, reply_markup=reply_markup
        )
        return msg.message_id

    async def send_nurse_dm(self, user_id: int, text: str) -> None:
        # Messaging → INFO
        self.log.info("msg.out.dm " + kv(user_id=user_id, text=text))
        await self.bot.send_message(chat_id=user_id, text=text)

    async def answer_callback(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False
    ) -> None:
        """Answer inline button press (ephemeral)."""
        await self.bot.answer_callback_query(
            callback_query_id, text=text or None, show_alert=show_alert
        )

    async def run_polling(self) -> None:
        self.log.debug("polling.run")
        await self.dp.start_polling(self.bot)

    # ------------------------------------------------------------------------------
    # v3 UI helpers
    # ------------------------------------------------------------------------------
    def build_patient_reply_kb(self, patient: dict) -> ReplyKeyboardMarkup:
        """
        Fixed reply keyboard for the patient.
        NOTE: Avoid selective=True in supergroups; it causes the keyboard to not show.
        """
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text=MESSAGES["btn_pressure"]),
                    KeyboardButton(text=MESSAGES["btn_weight"]),
                ],
                [KeyboardButton(text=MESSAGES["btn_help"])],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Виберіть дію або введіть значення...",
        )
        return kb

    def build_confirm_inline_kb(self, dose_key: DoseKey) -> InlineKeyboardMarkup:
        """Inline 'confirm taken' button attached to reminder/retry messages."""
        data = f"confirm:{dose_key.patient_id}:{dose_key.date_str}:{dose_key.time_str}"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=MESSAGES["btn_confirm_taken"], callback_data=data
                    )
                ]
            ]
        )
        return kb

    def build_force_reply(self) -> ForceReply:
        """ForceReply for guided input; selective=True as per spec."""
        return ForceReply(selective=True)

    async def refresh_reply_keyboard(
        self, patient: dict, group_id: int | None = None
    ) -> Optional[int]:
        """
        Send a tiny follow-up message with the fixed reply keyboard to "refresh" it.
        Use visible text so clients don't drop it.
        Returns the sent message_id (or None on failure).
        """
        gid = group_id or patient["group_id"]
        try:
            text = "Оновив кнопки ↓"
            kb = self.build_patient_reply_kb(patient)
            self.log.info(
                "msg.out.group " + kv(group_id=gid, text="(keyboard refresh)")
            )
            msg = await self.bot.send_message(chat_id=gid, text=text, reply_markup=kb)
            return msg.message_id
        except Exception as e:
            self.log.error(
                "msg.out.group.error "
                + kv(group_id=gid, err=str(e), where="refresh_reply_keyboard")
            )
            return None


__all__ = [
    "TelegramAdapter",
    "IncomingMessage",
    "DoseKey",
]
