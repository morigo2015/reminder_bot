# pillsbot/core/reminder_messaging.py
from __future__ import annotations

import logging
from typing import Any, Optional

from pillsbot.core.i18n import fmt, MESSAGES
from pillsbot.core.logging_utils import kv
from pillsbot.core.reminder_state import DoseInstance


class ReminderMessenger:
    """
    Handles all outbound UX. In v4, there is a single flat menu message
    at the bottom of the chat. Before posting a new menu, the old one is deleted.
    """

    def __init__(
        self,
        adapter: Any | None,
        log: logging.Logger,
        inline_confirm_enabled: bool = True,  # kept for compatibility; not used in v4 logic
    ):
        self.adapter = adapter
        self.log = log
        self.inline_confirm_enabled = inline_confirm_enabled

    # -- v4 menu ---------------------------------------------------------
    async def send_menu(
        self, group_id: int, *, text: str, can_confirm: bool
    ) -> Optional[int]:
        """
        Ask the adapter to post the single menu message (delete old → post new).
        Returns new message_id when available.
        """
        if self.adapter is None or not hasattr(self.adapter, "send_menu_message"):
            return await self._send_group(group_id, text)
        try:
            return await self.adapter.send_menu_message(
                group_id, text, can_confirm=can_confirm
            )
        except Exception as e:  # defensive
            self.log.error("menu.send.error " + kv(group_id=group_id, err=str(e)))
            return await self._send_group(group_id, text)

    async def send_reminder_step(self, inst: DoseInstance) -> Optional[int]:
        """Send reminder text + menu with confirm."""
        return await self.send_menu(
            inst.group_id, text=MESSAGES["reminder_text"], can_confirm=True
        )

    async def send_home_step(
        self, group_id: int, patient_id: int, *, can_confirm: bool
    ) -> Optional[int]:
        """Send idle text + menu (confirm only if can_confirm=True)."""
        return await self.send_menu(
            group_id, text=MESSAGES["idle_text"], can_confirm=can_confirm
        )

    # -- other messaging -------------------------------------------------
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

    async def send_nurse_notice(self, user_id: int, text: str) -> None:
        await self._send_nurse_dm(user_id, text)

    # -- low-level adapter calls with fallbacks --------------------------
    async def _send_group(
        self, group_id: int, text: str, reply_markup: Any | None = None
    ) -> Optional[int]:
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
            msg = await self.adapter.send_group_message(
                group_id, text, reply_markup=reply_markup
            )
            return getattr(msg, "message_id", None)
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
