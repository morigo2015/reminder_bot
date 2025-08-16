# pillsbot/adapters/telegram_adapter.py
from __future__ import annotations

import asyncio
import logging
import contextlib
from typing import Any, Iterable

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
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
from pillsbot.debug_ids import print_group_and_users_best_effort


class TelegramAdapter:
    """
    Aiogram 3.x adapter implementing the v4 inline-only UX:

    • Single dynamic inline menu at the bottom (flat, no submenus, no pinned message).
    • Exactly one menu message exists in the chat: before posting a new one, delete the old one.
    • Accept both tap and text confirmation (engine handles text; adapter routes taps).
    • Patient-only actions; others are ignored (now with a polite toast + INFO log).
    """

    def __init__(
        self, bot_token: str, engine: Any, patient_groups: Iterable[int]
    ) -> None:
        self.bot = Bot(token=bot_token, parse_mode=None)
        self.dp = Dispatcher()

        self.engine = engine
        self.patient_groups = set(patient_groups)

        self.log = logging.getLogger("pillsbot.adapter")

        # Per-chat menu lifecycle (v4: delete-then-post)
        self._last_menu_msg_id: dict[int, int] = {}
        # per-chat lock to serialize delete→post across concurrent sends
        self._menu_locks: dict[int, asyncio.Lock] = {}

        # ---- Handlers (IMPORTANT: commands first, then generic text) ----
        self.dp.message.register(self.on_start, CommandStart())
        self.dp.message.register(self.on_ids, Command("ids"))
        self.dp.message.register(self.on_group_text, F.text)
        self.dp.callback_query.register(self.on_callback, F.data.startswith("ui:"))

    # ------------------------------------------------------------------------------
    # Flat inline keyboard (single component; can_confirm toggles first row)
    # ------------------------------------------------------------------------------
    def build_menu_keyboard(self, *, can_confirm: bool) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []

        if can_confirm:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="✅ " + MESSAGES["btn_confirm_taken"],
                        callback_data="ui:TAKE",
                    )
                ]
            )

        rows.append(
            [
                InlineKeyboardButton(
                    text=MESSAGES["btn_pressure"], callback_data="ui:PRESSURE"
                ),
                InlineKeyboardButton(
                    text=MESSAGES["btn_weight"], callback_data="ui:WEIGHT"
                ),
            ]
        )
        rows.append(
            [InlineKeyboardButton(text=MESSAGES["btn_help"], callback_data="ui:HELP")]
        )

        return InlineKeyboardMarkup(inline_keyboard=rows)

    # ------------------------------------------------------------------------------
    # Menu posting (delete previous first) — serialized per chat
    # ------------------------------------------------------------------------------
    async def post_menu(self, chat_id: int, text: str, *, can_confirm: bool) -> int:
        lock = self._menu_locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            old = self._last_menu_msg_id.get(chat_id)
            if old:
                try:
                    await self.bot.delete_message(chat_id, old)
                except Exception as e:
                    self.log.debug(
                        "menu.delete.fail " + kv(chat_id=chat_id, err=str(e))
                    )

            kb = self.build_menu_keyboard(can_confirm=can_confirm)
            msg = await self.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=kb
            )

            self._last_menu_msg_id[chat_id] = msg.message_id
            return msg.message_id

    # ------------------------------------------------------------------------------
    # Reply keyboard removal — done on /start (separate message)
    # ------------------------------------------------------------------------------
    async def clear_reply_keyboard_once(self, chat_id: int) -> None:
        try:
            await self.bot.send_message(
                chat_id,
                "Оновлення інтерфейсу…",
                reply_markup=ReplyKeyboardRemove(remove_keyboard=True),
            )
        except Exception:
            # Best-effort, ignore any errors (no rights, etc.)
            pass

    # ------------------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------------------
    async def on_start(self, message: Message) -> None:
        chat_id = message.chat.id
        await self.clear_reply_keyboard_once(chat_id)
        await self.engine.show_current_menu(chat_id)

    async def on_group_text(self, message: Message) -> None:
        chat_id = message.chat.id
        text = message.text or ""
        sender_user_id = message.from_user.id if message.from_user else 0

        # Fallback guard: if a command slipped through, route it explicitly
        if text.startswith("/"):
            cmd = text.split()[0].split("@")[0].lower()
            if cmd == "/start":
                await self.on_start(message)
                return
            if cmd == "/ids":
                await self.on_ids(message)
                return

        self.log.info(
            "msg.in.group "
            + kv(group_id=chat_id, sender_user_id=sender_user_id, text=text)
        )

        if chat_id not in self.patient_groups:
            self.log.debug("msg.in.ignored " + kv(reason="not a patient group"))
            return

        sent_at_utc = getattr(message, "date", None)
        if sent_at_utc is None:
            from datetime import datetime, timezone as _tz

            sent_at_utc = datetime.now(_tz.utc)

        incoming = IncomingMessage(
            group_id=chat_id,
            sender_user_id=sender_user_id,
            text=text,
            sent_at_utc=sent_at_utc,
        )

        await self.engine.on_patient_message(incoming)

    async def on_callback(self, callback: CallbackQuery) -> None:
        """
        Flat UI actions:
        - ui:TAKE      → confirm (if awaiting)
        - ui:PRESSURE  → show hint + menu in ONE message; expect next input as pressure
        - ui:WEIGHT    → show hint + menu in ONE message; expect next input as weight
        - ui:HELP      → help text, then refresh menu

        Only the mapped patient may act. Others get a polite toast and we log at INFO.
        """
        chat_id = callback.message.chat.id if callback.message else 0
        from_user_id = callback.from_user.id if callback.from_user else 0
        data = callback.data or ""

        # Access control: patient-only
        expected_pid = None
        pid_mapping = getattr(self.engine, "group_to_patient", None)
        if isinstance(pid_mapping, dict):
            expected_pid = pid_mapping.get(chat_id)
        if expected_pid is not None and from_user_id != expected_pid:
            # Toast the tapper so they understand why "nothing happens"
            with contextlib.suppress(Exception):
                await callback.answer(
                    "Ця кнопка доступна лише пацієнту.", show_alert=False
                )
            # Log at INFO so it's visible in default console output
            self.log.info(
                "cb.ignored.nonpatient "
                + kv(
                    group_id=chat_id,
                    actor=from_user_id,
                    expected=expected_pid,
                    action=data,
                )
            )
            return

        # Acknowledge the callback to clear the Telegram spinner
        try:
            await callback.answer()
        except Exception:
            pass

        # Route actions
        if data == "ui:TAKE":
            await self.engine.quick_confirm(chat_id, from_user_id)
            return

        if data == "ui:PRESSURE":
            await self.engine.show_hint_menu(chat_id, kind="pressure")
            return

        if data == "ui:WEIGHT":
            await self.engine.show_hint_menu(chat_id, kind="weight")
            return

        if data == "ui:HELP":
            await self.engine.show_help(chat_id)
            return

    async def on_ids(self, message: Message) -> None:
        """
        Debug command: /ids prints group id and best-effort participants to console only.
        No chat output, no menu refresh or deletions.
        """
        try:
            known_ids: set[int] = set()
            chat_id = message.chat.id

            pid_mapping = getattr(self.engine, "group_to_patient", {})
            pat_idx = getattr(self.engine, "patient_index", {})

            patient_id = pid_mapping.get(chat_id)
            if isinstance(patient_id, int):
                known_ids.add(patient_id)
                pdata = pat_idx.get(patient_id, {})
                nurse_id = pdata.get("nurse_user_id")
                if isinstance(nurse_id, int):
                    known_ids.add(nurse_id)

            await print_group_and_users_best_effort(
                self.bot, message, known_user_ids=list(known_ids)
            )
        except Exception as e:
            self.log.debug("ids.print.fail " + kv(err=str(e)))
        # Intentionally do nothing in chat (no reply).

    # ------------------------------------------------------------------------------
    # Outbound messaging (used by messenger)
    # ------------------------------------------------------------------------------
    async def send_group_message(
        self, group_id: int, text: str, reply_markup: Any | None = None
    ) -> int:
        self.log.info("msg.out.group " + kv(group_id=group_id, text=text))
        msg = await self.bot.send_message(
            chat_id=group_id, text=text, reply_markup=reply_markup
        )
        return msg.message_id

    async def send_nurse_dm(self, user_id: int, text: str) -> None:
        self.log.info("msg.out.dm " + kv(user_id=user_id, text=text))
        await self.bot.send_message(chat_id=user_id, text=text)

    # v4 menu hook used by ReminderMessenger
    async def send_menu_message(
        self, group_id: int, text: str, *, can_confirm: bool
    ) -> int:
        return await self.post_menu(group_id, text, can_confirm=can_confirm)

    async def run_polling(self) -> None:
        self.log.debug("polling.run")
        await self.bot.delete_webhook(drop_pending_updates=True)
        await self.dp.start_polling(self.bot)


__all__ = [
    "TelegramAdapter",
    "IncomingMessage",
]
