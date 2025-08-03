"""Very lightweight confirmation handler: look for event_name in any text."""

from aiogram import Router
from aiogram.types import Message

from ..services.reminder_manager import ReminderManager, _STATE


def setup_confirmation_handlers(router: Router, rm: ReminderManager) -> None:
    @router.message()
    async def _confirm(message: Message):
        text = (message.text or "").strip()
        # Iterate through active reminders and match by event_name
        for (chat_id, ev_name), state in list(_STATE.items()):
            if chat_id == message.chat.id and ev_name in text:
                rm.mark_confirmed(chat_id, ev_name)
                await message.answer("✅ Thank you for confirming!")
                return
