import re
import logging
from aiogram import Router, types
from reminder_bot.config.dialogs_loader import RAW_PATTERNS, DIALOGS
from reminder_bot.services.reminder_manager import _STATE, ReminderManager

router = Router()
logger = logging.getLogger(__name__)

# Build one anchored regex from raw YAML strings
raw_confirmation = RAW_PATTERNS.get('confirmation_ok', [])  # list[str]
union = '|'.join(raw_confirmation)
CONFIRM_REGEX = re.compile(rf'^(?:{union})$', re.IGNORECASE)

def is_confirmation(message: types.Message) -> bool:
    raw = message.text or ""
    text = raw.strip()
    logger.debug("Raw user text for confirmation: %r", raw)
    match = bool(CONFIRM_REGEX.match(text))
    logger.debug("CONFIRM_REGEX.match(%r) -> %s", text, match)
    return match

def setup_confirmation_handlers(dp, rm: ReminderManager):
    @router.message(is_confirmation)
    async def _confirm(message: types.Message):
        chat_id = message.chat.id
        pending = [
            ev_name
            for (cid, ev_name), st in _STATE.items()
            if cid == chat_id and not st.confirmed
        ]
        if not pending:
            logger.debug("No pending events to confirm for %s", chat_id)
            return

        for ev in pending:
            rm.mark_confirmed(chat_id, ev)
            logger.debug("Event '%s' confirmed for chat %s via %r", ev, chat_id, message.text)

        await message.reply("✅ Дякую, підтверджено.")

    dp.include_router(router)