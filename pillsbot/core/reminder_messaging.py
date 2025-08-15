# pillsbot/core/reminder_messaging.py
from __future__ import annotations

from typing import Any

from pillsbot.core.i18n import MESSAGES
from pillsbot.core.reminder_state import DoseInstance


class ReminderMessenger:
    """
    Thin messaging layer that keeps the invariant:
    The last visible message in the group is always the SINGLE inline menu
    (adapter deletes the previous menu, then posts the new one).
    """

    def __init__(self, adapter: Any, log: Any):
        self.adapter = adapter
        self.log = log

    # ------------------- generic helpers -------------------
    async def send_group_template(self, group_id: int, template_key: str, **kwargs) -> int:
        text = (
            MESSAGES[template_key].format(**kwargs)
            if kwargs
            else MESSAGES[template_key]
        )
        return await self.adapter.send_group_message(group_id, text)

    async def send_menu(self, group_id: int, *, text: str, can_confirm: bool) -> int:
        """
        Send ONE message that includes both the text and the inline keyboard.
        Adapter ensures delete-then-post.
        """
        return await self.adapter.send_menu_message(group_id, text, can_confirm=can_confirm)

    async def send_nurse_notice(self, nurse_user_id: int, text: str) -> None:
        await self.adapter.send_nurse_dm(nurse_user_id, text)

    # ------------------- composed steps -------------------
    async def send_reminder_step(self, inst: DoseInstance) -> None:
        """
        Reminder message with confirm button visible (AWAITING only).
        """
        await self.send_menu(inst.group_id, text=MESSAGES["reminder_text"], can_confirm=True)

    async def send_home_step(self, group_id: int, *, can_confirm: bool) -> None:
        """
        Idle home message, usually without confirm, but can_confirm is parametric.
        """
        await self.send_menu(group_id, text=MESSAGES["idle_text"], can_confirm=can_confirm)
