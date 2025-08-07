# handlers/confirmation.py

import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from config.dialogs_loader import RAW_CONFIG
from states import ReminderStates

logger = logging.getLogger(__name__)
router = Router()

_OK_SET = set()
for entry in RAW_CONFIG["patterns"]["confirmation_ok"]:
    pat = entry.strip().lstrip("^").rstrip("$")
    if pat.startswith("(") and pat.endswith(")"):
        pat = pat[1:-1]
    for choice in pat.split("|"):
        _OK_SET.add(choice.strip().lower())


def is_confirm(text: str) -> bool:
    return text.strip().lower() in _OK_SET


@router.message(
    StateFilter(ReminderStates.waiting_confirmation),
    F.text.func(is_confirm),
)
async def handle_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    event_name = data["event"]
    chat_id = message.chat.id
    user_id = message.from_user.id

    logger.debug(f"[CONFIRM] '{message.text}' → cancel '{event_name}'")
    manager = state.dispatcher["reminder_manager"]
    await manager.cancel_flow(event_name, chat_id, user_id)
    await message.reply("Дякую, підтверджено! ✅")


@router.message(
    StateFilter(ReminderStates.waiting_clarification),
    F.text.func(is_confirm),
)
async def handle_clarification_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    event_name = data["event"]
    chat_id = message.chat.id
    user_id = message.from_user.id

    logger.debug(f"[CLARIFY] '{message.text}' → finalize '{event_name}'")
    manager = state.dispatcher["reminder_manager"]
    await manager.finalize_flow(event_name, chat_id, user_id)
    await message.reply("Дякую за відповідь! 👍")
