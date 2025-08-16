# pillsbot/core/reminder_messaging.py
from __future__ import annotations

from typing import Any
from datetime import datetime

from pillsbot.core.i18n import MESSAGES, fmt
from pillsbot.core.reminder_state import DoseInstance  # type: ignore


class ReminderMessenger:
    """
    Messaging layer that enforces:
    - Contentful lines are standalone, persistent group messages.
    - The last visible message is the SINGLE inline menu (adapter deletes the previous menu).
    - Backward-compatible API surface for the v4 engine (e.g., send_group_template).
    """

    def __init__(self, adapter: Any, log: Any) -> None:
        self.adapter = adapter
        self.log = log

    # ------------------- low-level -------------------
    async def send_group_line(self, group_id: int, text: str) -> int:
        """Send a raw, contentful line (persistent)."""
        return await self.adapter.send_group_message(group_id, text)

    async def send_group_template(self, group_id: int, key: str, **kwargs) -> int:
        """
        v4-compat: resolve an i18n template by key, then send as a persistent group line.
        This method intentionally does NOT post/refresh the menu; engine controls when to show the menu.
        """
        # Prefer explicit key lookup; if missing, fall back to formatting the key itself.
        try:
            text_tmpl = MESSAGES[key]
            text = text_tmpl.format(**kwargs)
        except KeyError:
            # Fallback: allow directly passing arbitrary templates through the same path.
            text = key.format(**kwargs) if kwargs else key
        return await self.send_group_line(group_id, text)

    async def send_menu(self, group_id: int, *, text: str, can_confirm: bool) -> int:
        """
        Post (or refresh) the menu. Adapter deletes the previous menu first.

        Adapter API compatibility:
        - Prefer v4-style 'post_menu(...)' if present.
        - Otherwise, fall back to 'send_menu_message(...)' if provided by the adapter.
        """
        if hasattr(self.adapter, "post_menu"):
            # v4 adapter API
            return await self.adapter.post_menu(
                group_id, text=text, can_confirm=can_confirm
            )
        elif hasattr(self.adapter, "send_menu_message"):
            # v5 adapter wrapper (if present)
            return await self.adapter.send_menu_message(
                group_id, text, can_confirm=can_confirm
            )
        raise AttributeError(
            "Adapter must provide 'post_menu' or 'send_menu_message' for menus"
        )

    async def send_nurse_notice(self, nurse_user_id: int, text: str) -> None:
        await self.adapter.send_nurse_dm(nurse_user_id, text)

    # ------------------- composed steps -------------------
    async def send_reminder_step(self, inst: DoseInstance) -> None:
        """
        Post a contentful reminder line (persisted) and then the actionable menu.
        Adds retry prefix for repeated attempts.
        """
        # Determine retry ordinal: first visible reminder is attempt 1 (no prefix).
        attempts = getattr(inst, "attempts_sent", 1) or 1
        retries = max(0, attempts - 1)
        base = fmt("reminder_line", pill_text=getattr(inst, "pill_text", ""))
        if retries > 0:
            line = fmt("reminder_retry_prefix", n=retries) + base
        else:
            line = base

        await self.send_group_line(inst.group_id, line)
        await self.send_menu(
            inst.group_id, text=MESSAGES["reminder_text"], can_confirm=True
        )

    async def send_home_step(self, group_id: int, *, can_confirm: bool) -> None:
        """Idle home message (technical/ephemeral text) inside the menu."""
        await self.send_menu(
            group_id, text=MESSAGES["idle_text"], can_confirm=can_confirm
        )

    async def send_escalation(self, inst: DoseInstance) -> None:
        """Send group escalation line (persisted) + DM to nurse, then refresh menu."""
        # Group message
        await self.send_group_line(inst.group_id, MESSAGES["escalate_group"])

        # DM to nurse
        dt: datetime = getattr(inst, "scheduled_dt_local", datetime.now())
        txt = fmt(
            "escalate_dm",
            patient_label=getattr(inst, "patient_label", ""),
            date=dt.strftime("%Y-%m-%d"),
            time=dt.strftime("%H:%M"),
            pill_text=getattr(inst, "pill_text", ""),
        )
        await self.send_nurse_notice(getattr(inst, "nurse_user_id", 0), txt)

        # Refresh menu as last message
        await self.send_home_step(inst.group_id, can_confirm=False)
