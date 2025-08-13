# pillsbot/core/reminder_messaging.py
from __future__ import annotations

import logging
from typing import Any, Optional

from pillsbot.core.i18n import fmt, MESSAGES
from pillsbot.core.logging_utils import kv
from pillsbot.core.reminder_state import DoseKey, DoseInstance

# Telegram-only types are optional; keep them encapsulated here.
try:
    from aiogram.types import (
        ReplyKeyboardMarkup,
        KeyboardButton,
        InlineKeyboardMarkup,
        InlineKeyboardButton,
        ForceReply,
    )
except Exception:  # pragma: no cover - optional dependency
    ReplyKeyboardMarkup = KeyboardButton = InlineKeyboardMarkup = (
        InlineKeyboardButton
    ) = ForceReply = None


class ReminderMessenger:
    """
    Handles all outbound UX: text templates, keyboards, inline buttons, and fallbacks.
    Engine calls this via simple methods and stays transport-agnostic.
    """

    def __init__(
        self,
        adapter: Any | None,
        log: logging.Logger,
        inline_confirm_enabled: bool = True,
    ):
        self.adapter = adapter
        self.log = log
        self.inline_confirm_enabled = inline_confirm_enabled

    # -- high-level helpers -------------------------------------------------------------
    async def send_reminder(
        self, inst: DoseInstance, template_key: str
    ) -> Optional[int]:
        """Send reminder/retry message; attach inline 'Confirm Taken' when enabled."""
        kb_inline = (
            self.build_confirm_inline_kb(inst.dose_key)
            if self.inline_confirm_enabled and self._has_telegram()
            else None
        )
        text = (
            fmt("reminder", pill_text=inst.pill_text)
            if template_key == "reminder"
            else fmt("repeat_reminder")
        )
        return await self._send_group(inst.group_id, text, reply_markup=kb_inline)

    async def send_group_template(
        self, group_id: int, template_key: str, **fmt_args: Any
    ) -> Optional[int]:
        """Send a plain templated group message (no buttons)."""
        text = fmt(template_key, **fmt_args)
        return await self._send_group(group_id, text, reply_markup=None)

    async def refresh_reply_keyboard(self, patient: dict) -> Optional[int]:
        """
        Refresh the fixed reply keyboard. Uses a visible text to make clients keep it.
        Always sets selective=True (your environment is a small private group).
        """
        if not self._has_telegram() or self.adapter is None:
            self.log.error(
                "keyboard.refresh.skip " + kv(reason="adapter or telegram missing")
            )
            return None
        try:
            kb = self.build_patient_reply_kb(patient, selective=True)
            msg_id = await self._send_group(
                patient["group_id"], "Оновив кнопки ↓", reply_markup=kb
            )
            return msg_id
        except Exception as e:  # pragma: no cover - adapter-level errors
            self.log.error(
                "keyboard.refresh.error "
                + kv(group_id=patient.get("group_id"), err=str(e))
            )
            return None

    async def send_escalation(self, inst: DoseInstance) -> None:
        """Group notice + DM to nurse."""
        await self._send_group(inst.group_id, MESSAGES["escalate_group"])
        await self._send_nurse_dm(
            inst.nurse_user_id,
            fmt(
                "escalate_dm",
                patient_label=inst.patient_label,
                date=inst.dose_key.date_str,
                time=inst.dose_key.time_str,
                pill_text=inst.pill_text,
            ),
        )

    # -- low-level adapter calls with fallbacks -----------------------------------------
    async def _send_group(
        self, group_id: int, text: str, reply_markup: Any | None = None
    ) -> Optional[int]:
        """
        Adapter compatibility: prefer (group_id, text, reply_markup); fallback to (group_id, text).
        Returns message_id when the adapter provides it; else None.
        """
        if self.adapter is None:
            self.log.error(
                "msg.out.group.error "
                + kv(group_id=group_id, err="adapter not attached")
            )
            return None

        try:
            self.log.info(
                "msg.out.group "
                + kv(
                    group_id=group_id, text=text[:64] + ("…" if len(text) > 64 else "")
                )
            )
            try:
                # preferred signature
                msg = await self.adapter.send_group_message(
                    group_id, text, reply_markup=reply_markup
                )  # type: ignore
                return getattr(msg, "message_id", None)
            except TypeError:
                # fallback signature (tests use this)
                _ = await self.adapter.send_group_message(group_id, text)  # type: ignore
                return None
        except Exception as e:  # pragma: no cover - adapter-level errors
            self.log.error("msg.out.group.error " + kv(group_id=group_id, err=str(e)))
            return None

    async def _send_nurse_dm(self, user_id: int, text: str) -> None:
        if self.adapter is None:
            self.log.error(
                "msg.out.dm.error " + kv(user_id=user_id, err="adapter not attached")
            )
            return
        try:
            self.log.info(
                "msg.out.dm "
                + kv(user_id=user_id, text=text[:64] + ("…" if len(text) > 64 else ""))
            )
            await self.adapter.send_nurse_dm(user_id, text)
        except Exception as e:  # pragma: no cover
            self.log.error("msg.out.dm.error " + kv(user_id=user_id, err=str(e)))

    # -- Telegram UI builders (encapsulated here) ---------------------------------------
    def _has_telegram(self) -> bool:
        return InlineKeyboardMarkup is not None

    def build_patient_reply_kb(
        self, patient: dict, *, selective: bool = True
    ) -> Any | None:
        """
        Persistent patient keyboard; selective=True so only the patient sees it.
        Kept here to isolate Telegram-specifics from the engine.
        """
        if ReplyKeyboardMarkup is None:  # non-Telegram channels
            return None
        return ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text=MESSAGES["btn_pressure"]),
                    KeyboardButton(text=MESSAGES["btn_weight"]),
                ],
                [KeyboardButton(text=MESSAGES["btn_help"])],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            is_persistent=True,
            selective=selective,
            input_field_placeholder="Виберіть дію або введіть значення…",
        )

    def build_confirm_inline_kb(self, dose_key: DoseKey) -> Any | None:
        """Inline 'confirm taken' button attached to reminder/retry messages."""
        if InlineKeyboardMarkup is None:
            return None
        data = f"confirm:{dose_key.patient_id}:{dose_key.date_str}:{dose_key.time_str}"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=MESSAGES["btn_confirm_taken"], callback_data=data
                    )
                ]
            ]
        )

    def build_force_reply(self) -> Any | None:
        """Guided input; selective=True for the patient."""
        if ForceReply is None:
            return None
        return ForceReply(selective=True)
