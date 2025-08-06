from aiogram import Router, F
from aiogram.types import Message

router = Router()
STATUS_COMMANDS = ["/status", "звіт", "report"]


@router.message(F.text.startswith(tuple(STATUS_COMMANDS)))
async def status_handler(message: Message):
    """Collects health-status messages and logs them with a rolling window."""
    log_service = message.bot.dispatcher["log_service"]
    await log_service.status(message.chat.id, message.text, dropped=False)
    await message.answer("📝 Status recorded.")
