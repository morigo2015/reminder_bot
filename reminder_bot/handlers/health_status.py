from aiogram import Router
from aiogram.filters import Text
from aiogram.types import Message
# from aiogram.fsm.context import FSMContext
# from reminder_bot.states import ReminderStates

router = Router()
STATUS_COMMANDS = ["/status", "звіт", "report"]


@router.message(Text(startswith=tuple(STATUS_COMMANDS), ignore_case=True))
async def status_handler(message: Message):
    """Collects health-status messages and logs them with a rolling window."""
    log_service = message.bot["log_service"]
    # Placeholder: windowing logic to group messages
    await log_service.status(message.chat.id, message.text, dropped=False)
    await message.answer("📝 Status recorded.")
