# pillsbot/core/reminder_messaging.py
from __future__ import annotations

import logging
from typing import Any, Optional

from pillsbot.core.i18n import fmt, MESSAGES
from pillsbot.core.logging_utils import kv
from pillsbot.core.reminder_state import DoseKey, DoseInstance

# Telegram-only types are optional; keep them encapsulated here.
try:
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton  # noqa:F401
except Exception:  # pragma: no cover - optional dependency
    InlineKeyboardMarkup = InlineKeyboardButton = None  # type: ignore


class ReminderMessenger:
    """
    Handles all outbound UX: text templates and inline buttons.
    UI is inline-only per pill_reminder_UI_guide.md.

    This layer **does not** auto-append menus after plain messages.
    The engine/adapters decide *when* a STEP (inline keyboard) is posted.
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
    async def send_reminder_step(self, inst: DoseInstance) -> Optional[int]:
        """
        Send the actionable STEP for a reminder (text + inline 'Confirm Taken').
        Retires the previous step before sending the new one (adapter responsibility).
        """
        if not self._has_telegram() or not self.inline_confirm_enabled:
            # Plain fallback (rare)
            return await self._send_group(
                inst.group_id,
                fmt("reminder", pill_text=inst.pill_text),
                reply_markup=None,
            )

        kb_inline = self.build_confirm_inline_kb(inst.dose_key)
        text = fmt("reminder", pill_text=inst.pill_text)

        if self.adapter is not None and hasattr(self.adapter, "send_step_message"):
            try:
                return await self.adapter.send_step_message(
                    inst.group_id, text, kb_inline
                )
            except TypeError:
                pass

        # Fallback: plain group message (no inline step)
        return await self._send_group(inst.group_id, text, reply_markup=kb_inline)

    async def send_group_template(
        self, group_id: int, template_key: str, **fmt_args: Any
    ) -> Optional[int]:
        """Send a plain templated group message (no buttons)."""
        text = fmt(template_key, **fmt_args)
        return await self._send_group(group_id, text, reply_markup=None)

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

    async def send_home_step(
        self, group_id: int, patient_id: int, *, can_confirm: bool
    ) -> Optional[int]:
        """
        Send the compact Home STEP (inline-only) at the bottom.
        The adapter builds a context-aware keyboard (confirm button only if can_confirm=True).
        """
        kb = None
        if self.adapter is not None and hasattr(self.adapter, "get_home_keyboard"):
            try:
                kb = self.adapter.get_home_keyboard(patient_id, can_confirm=can_confirm)  # type: ignore[arg-type]
            except TypeError:
                # Backward compatibility with older signature: get_home_keyboard(patient_id)
                kb = self.adapter.get_home_keyboard(patient_id)  # type: ignore[misc]
        if self.adapter is not None and hasattr(self.adapter, "send_step_message"):
            try:
                return await self.adapter.send_step_message(
                    group_id, MESSAGES["home_title"], kb
                )
            except TypeError:
                pass
        return await self._send_group(group_id, MESSAGES["home_title"])

    async def send_nurse_notice(self, user_id: int, text: str) -> None:
        """Public wrapper to DM nurse (used for late-confirm notices)."""
        await self._send_nurse_dm(user_id, text)

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
                msg = await self.adapter.send_group_message(
                    group_id, text, reply_markup=reply_markup
                )  # type: ignore
                return getattr(msg, "message_id", None)
            except TypeError:
                _ = await self.adapter.send_group_message(group_id, text)  # type: ignore
                return None
        except Exception as e:  # pragma: no cover
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

    def build_confirm_inline_kb(self, dose_key: DoseKey) -> Any | None:
        """Inline 'confirm taken' button attached to reminder/retry STEP."""
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
