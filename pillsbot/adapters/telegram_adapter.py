# pillsbot/adapters/telegram_adapter.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)

from pillsbot.core.reminder_engine import IncomingMessage
from pillsbot.core.logging_utils import kv
from pillsbot.core.i18n import MESSAGES


class TelegramAdapter:
    """
    aiogram 3.x adapter with inline-only UI per pill_reminder_UI_guide.md:
    - Pinned Home message is STATIC (no buttons)
    - Exactly one actionable STEP at a time (retire previous before sending)
    - Robust patient guard (accepts payload pid or mapped pid)
    - No ReplyKeyboard ever shown
    """

    def __init__(
        self, bot_token: str, engine: Any, patient_groups: Iterable[int]
    ) -> None:
        self.bot = Bot(token=bot_token, parse_mode=None)
        self.dp = Dispatcher()

        self.engine = engine
        self.patient_groups = set(patient_groups)

        self.log = logging.getLogger("pillsbot.adapter")

        # Per-chat UI state
        self._home_msg_id: dict[int, int] = {}
        self._last_step_msg_id: dict[int, int] = {}
        self._reply_kb_cleared: set[int] = set()

        # Handlers
        self.dp.message.register(self.on_group_text, F.text)
        self.dp.message.register(self.on_start, CommandStart())
        self.dp.callback_query.register(
            self.on_callback, F.data.startswith(("confirm:", "ui:"))
        )

    # ------------------------------------------------------------------------------
    # Inline keyboards (helpers)
    # ------------------------------------------------------------------------------
    def kb(self, rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=label, callback_data=data)
                    for (label, data) in row
                ]
                for row in rows
            ]
        )

    def home_keyboard(
        self, patient_id: int, *, can_confirm: bool
    ) -> InlineKeyboardMarkup:
        rows: list[list[tuple[str, str]]] = []
        if can_confirm:
            rows.append(
                [("✅ " + MESSAGES["btn_confirm_taken"], f"ui:TAKE:{patient_id}")]
            )
        rows.append([("📈 " + MESSAGES["btn_measurements"], f"ui:MEAS:{patient_id}")])
        rows.append([("🆘 " + MESSAGES["btn_help"], f"ui:HELP:{patient_id}")])
        return self.kb(rows)

    def get_home_keyboard(
        self, patient_id: int, *, can_confirm: bool
    ) -> InlineKeyboardMarkup:
        """Public for messenger/engine to obtain the context-aware Home keyboard."""
        return self.home_keyboard(patient_id, can_confirm=can_confirm)

    def measurements_keyboard(self, patient_id: int) -> InlineKeyboardMarkup:
        return self.kb(
            [
                [
                    (MESSAGES["btn_pressure"], f"ui:MEAS_P:{patient_id}"),
                    (MESSAGES["btn_weight"], f"ui:MEAS_W:{patient_id}"),
                ],
                [(MESSAGES["btn_back_home"], f"ui:HOME:{patient_id}")],
            ]
        )

    # ------------------------------------------------------------------------------
    # Reply keyboard removal (one-time per chat)
    # ------------------------------------------------------------------------------
    async def clear_reply_keyboard(self, chat_id: int) -> None:
        if chat_id in self._reply_kb_cleared:
            return
        try:
            await self.bot.send_message(
                chat_id, " ", reply_markup=ReplyKeyboardRemove(remove_keyboard=True)
            )
        except Exception:
            pass
        self._reply_kb_cleared.add(chat_id)

    # ------------------------------------------------------------------------------
    # Pinned Home (STATIC) & Step sending
    # ------------------------------------------------------------------------------
    async def ensure_pinned_home(self, chat_id: int, patient_id: Optional[int]) -> None:
        if patient_id is None:
            return

        mid = self._home_msg_id.get(chat_id)
        if mid:
            try:
                await self.bot.pin_chat_message(
                    chat_id=chat_id, message_id=mid, disable_notification=True
                )
                return
            except Exception:
                pass

        # STATIC pinned message with NO INLINE KEYBOARD
        msg = await self.bot.send_message(
            chat_id,
            MESSAGES["home_title"],
            reply_markup=ReplyKeyboardRemove(remove_keyboard=True),
        )
        self._home_msg_id[chat_id] = msg.message_id
        try:
            await self.bot.pin_chat_message(
                chat_id=chat_id, message_id=msg.message_id, disable_notification=True
            )
        except Exception:
            pass

    async def retire_old_keyboard(self, chat_id: int) -> None:
        mid = self._last_step_msg_id.get(chat_id)
        if not mid:
            return
        try:
            await self.bot.edit_message_reply_markup(chat_id, mid, reply_markup=None)
        except Exception:
            pass

    async def send_step_message(
        self, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None
    ) -> int:
        await self.retire_old_keyboard(chat_id)
        msg = await self.bot.send_message(chat_id, text, reply_markup=reply_markup)
        self._last_step_msg_id[chat_id] = msg.message_id
        return msg.message_id

    # ------------------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------------------
    async def on_start(self, message: Message) -> None:
        chat_id = message.chat.id
        pid_mapping = getattr(self.engine, "group_to_patient", None)
        pid = pid_mapping.get(chat_id) if isinstance(pid_mapping, dict) else None
        await self.ensure_pinned_home(chat_id, pid)
        await self.clear_reply_keyboard(chat_id)
        # On start, send Home STEP (no confirm) immediately
        if isinstance(pid_mapping, dict) and pid is not None:
            await self.send_step_message(
                chat_id,
                MESSAGES["home_title"],
                self.home_keyboard(pid, can_confirm=False),
            )

    async def on_group_text(self, message: Message) -> None:
        chat_id = message.chat.id
        text = message.text or ""
        sender_user_id = message.from_user.id if message.from_user else 0

        self.log.info(
            "msg.in.group "
            + kv(group_id=chat_id, sender_user_id=sender_user_id, text=text)
        )

        if chat_id not in self.patient_groups:
            self.log.debug("msg.in.ignored " + kv(reason="not a patient group"))
            return

        sent_at_utc = getattr(message, "date", None) or datetime.now(timezone.utc)

        incoming = IncomingMessage(
            group_id=chat_id,
            sender_user_id=sender_user_id,
            text=text,
            sent_at_utc=sent_at_utc,
        )

        pid_mapping = getattr(self.engine, "group_to_patient", None)
        pid = pid_mapping.get(chat_id) if isinstance(pid_mapping, dict) else None
        await self.ensure_pinned_home(chat_id, pid)
        await self.clear_reply_keyboard(chat_id)

        await self.engine.on_patient_message(incoming)

    async def on_callback(self, callback: CallbackQuery) -> None:
        chat_id = callback.message.chat.id if callback.message else 0
        from_user_id = callback.from_user.id if callback.from_user else 0
        data = callback.data or ""
        msg_id = callback.message.message_id if callback.message else None

        # Parse pid from payload when present (for robust guard)
        payload_pid: Optional[int] = None
        try:
            if data.startswith("confirm:"):
                _, pid_s, *_ = data.split(":")
                payload_pid = int(pid_s)
            elif data.startswith("ui:"):
                _, _, pid_s = (data.split(":") + ["", "", ""])[:3]
                if pid_s.isdigit():
                    payload_pid = int(pid_s)
        except Exception:
            payload_pid = None

        # Group guard — allow if mapping OR payload pid matches the actor
        expected_pid = None
        pid_mapping = getattr(self.engine, "group_to_patient", None)
        if isinstance(pid_mapping, dict):
            expected_pid = pid_mapping.get(chat_id)

        is_actor_patient = (
            (expected_pid is not None and from_user_id == expected_pid)
            or (payload_pid is not None and from_user_id == payload_pid)
            or (expected_pid is None and payload_pid is None)
        )
        if not is_actor_patient:
            await self.answer_callback(
                callback.id, text=MESSAGES["cb_only_patient"], show_alert=True
            )
            return

        # Home/submenu actions (ui:*)
        if data.startswith("ui:"):
            await self.answer_callback(
                callback.id, text=MESSAGES["toast_processing"], show_alert=False
            )
            _, action, pid_str = (data.split(":") + ["", "", ""])[:3]

            if action == "TAKE":
                await self.engine.quick_confirm(chat_id, from_user_id)
                # Do NOT auto-show next reminder/menu; engine sends only confirm_ack
                return

            if action == "HELP":
                await self.engine._reply(chat_id, "help_brief")
                return

            if action == "MEAS":
                pid = int(pid_str) if pid_str.isdigit() else from_user_id
                await self.send_step_message(
                    chat_id,
                    MESSAGES["measurements_menu_title"],
                    self.measurements_keyboard(pid),
                )
                return

            if action == "MEAS_P":
                await self.engine._reply(chat_id, "prompt_pressure")
                return

            if action == "MEAS_W":
                await self.engine._reply(chat_id, "prompt_weight")
                return

            if action == "HOME":
                # Show context-aware bottom STEP:
                # - Confirm ONLY if awaiting, else Home without confirm
                await self.engine.show_current_menu(chat_id)
                return

            return

        # Step actions (confirm:*). Outdated tap?
        if (
            msg_id is not None
            and self._last_step_msg_id.get(chat_id)
            and msg_id != self._last_step_msg_id[chat_id]
        ):
            await self.answer_callback(
                callback.id, text=MESSAGES["toast_expired"], show_alert=False
            )
            await self.engine.show_current_menu(chat_id)
            return

        await self.answer_callback(
            callback.id, text=MESSAGES["toast_processing"], show_alert=False
        )
        try:
            if msg_id is not None:
                await self.bot.edit_message_reply_markup(
                    chat_id, msg_id, reply_markup=None
                )
        except Exception:
            pass

        result: dict[str, Any] = await self.engine.on_inline_confirm(
            group_id=chat_id, from_user_id=from_user_id, data=data, message_id=msg_id
        )

        cb_text: Optional[str] = result.get("cb_text")
        show_alert: bool = bool(result.get("show_alert", False))
        if cb_text:
            await self.answer_callback(callback.id, text=cb_text, show_alert=show_alert)

    # ------------------------------------------------------------------------------
    # Outbound messaging
    # ------------------------------------------------------------------------------
    async def send_group_message(
        self, group_id: int, text: str, reply_markup: Any | None = None
    ) -> int:
        self.log.info("msg.out.group " + kv(group_id=group_id, text=text))
        if reply_markup is None:
            reply_markup = ReplyKeyboardRemove(remove_keyboard=True)
        msg = await self.bot.send_message(
            chat_id=group_id, text=text, reply_markup=reply_markup
        )
        return msg.message_id

    async def send_nurse_dm(self, user_id: int, text: str) -> None:
        self.log.info("msg.out.dm " + kv(user_id=user_id, text=text))
        await self.bot.send_message(chat_id=user_id, text=text)

    async def answer_callback(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False
    ) -> None:
        await self.bot.answer_callback_query(
            callback_query_id, text=text or None, show_alert=show_alert
        )

    async def run_polling(self) -> None:
        self.log.debug("polling.run")
        await self.bot.delete_webhook(drop_pending_updates=True)
        await self.dp.start_polling(self.bot)


__all__ = [
    "TelegramAdapter",
    "IncomingMessage",
]
