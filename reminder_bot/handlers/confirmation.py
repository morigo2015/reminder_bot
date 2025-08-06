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

# ────────────────────────────────────────────────────────────────────────────
# Build a set of literal “OK” words from your YAML patterns
# ────────────────────────────────────────────────────────────────────────────
_OK_SET = set()
for entry in RAW_CONFIG["patterns"]["confirmation_ok"]:
    pat = entry.strip()  # trim whitespace
    pat = pat.lstrip("^").rstrip("$")  # remove anchors
    if pat.startswith("(") and pat.endswith(")"):
        pat = pat[1:-1]  # unwrap group
    for choice in pat.split("|"):
        _OK_SET.add(choice.strip().lower())

logger.debug(f"[CONF] Acceptable words: {_OK_SET}")  # shows once at startup


def is_confirm(text: str) -> bool:
    """Return True if message text is one of the allowed confirmation words."""
    return text.strip().lower() in _OK_SET


# ────────────────────────────────────────────────────────────────────────────
# Handler: confirmation during initial waiting_confirmation phase
# ────────────────────────────────────────────────────────────────────────────
@router.message(
    StateFilter(ReminderStates.waiting_confirmation),
    F.text.func(is_confirm),
)
async def handle_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    event_name = data.get("event")
    chat_id = message.chat.id

    manager = state.dispatcher["reminder_manager"]
    logger.debug(
        f"[CONFIRMATION] '{message.text}' accepted; canceling flow '{event_name}'"
    )

    await manager.cancel_flow(event_name, chat_id)
    await message.reply("Дякую, підтверджено! ✅")


# ────────────────────────────────────────────────────────────────────────────
# Handler: confirmation during clarification phase
# ────────────────────────────────────────────────────────────────────────────
@router.message(
    StateFilter(ReminderStates.waiting_clarification),
    F.text.func(is_confirm),
)
async def handle_clarification_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    event_name = data.get("event")
    chat_id = message.chat.id

    manager = state.dispatcher["reminder_manager"]
    logger.debug(
        f"[CLARIFICATION] '{message.text}' accepted; finalizing flow '{event_name}'"
    )

    await manager.finalize_flow(event_name, chat_id)
    await message.reply("Дякую за відповідь! 👍")


# ────────────────────────────────────────────────────────────────────────────
# TEMPORARY DEBUG HANDLER — prints every incoming text with the FSM state.
# Delete this once you confirm the above two handlers are firing.
# ────────────────────────────────────────────────────────────────────────────
@router.message()
async def _debug_log(message: Message, state: FSMContext):
    current_state = await state.get_state()
    logger.warning(f"[DEBUG] text={message.text!r}, FSM-state={current_state}")
