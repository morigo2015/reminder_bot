import logging
from aiogram import Router, types
from reminder_bot.config.dialogs_loader import DIALOGS
from reminder_bot.services.reminder_manager import _STATE

router = Router()
logger = logging.getLogger(__name__)

@router.message()
async def fallback_handler(message: types.Message):
    chat_id = message.chat.id
    # Only prompt clarify if there's a pending unconfirmed event
    pending = [
        (cid, ev)
        for (cid, ev), state in _STATE.items()
        if cid == chat_id and not state.confirmed
    ]
    if not pending:
        logger.debug("No pending events for chat %s; ignoring message.", chat_id)
        return
    # Send clarification prompt
    clarify_text = DIALOGS['messages']['reminder']['clarify']
    logger.debug("Sending clarify prompt to chat %s: %s", chat_id, clarify_text)
    await message.reply(clarify_text)

