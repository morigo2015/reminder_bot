"""Handle escalation to nurse when reminders fail."""
import logging
from aiogram import Bot
from reminder_bot.config import NURSE_CHAT_ID
from reminder_bot.config.dialogs_loader import DIALOGS

logger = logging.getLogger(__name__)

async def escalate(bot: Bot, event_name: str, chat_id: int, attempts: int) -> None:
    """Notify the nurse when an event has exhausted retries without confirmation."""
    template = DIALOGS['messages']['nurse']['clarification_failed']
    text = template.format(event_name=event_name, attempts=attempts)
    try:
        await bot.send_message(NURSE_CHAT_ID, text)
        logger.debug(
            "Escalated event '%s' for chat %s to nurse %s after %d attempts",
            event_name, chat_id, NURSE_CHAT_ID, attempts
        )
    except Exception as e:
        logger.error(
            "Failed to escalate event '%s' for chat %s: %s",
            event_name, chat_id, e
        )