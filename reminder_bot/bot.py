import asyncio
import logging
from reminder_bot.config import BOT_TOKEN

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from reminder_bot.events import EVENTS
from reminder_bot.services.reminder_manager import ReminderManager
from reminder_bot.scheduler import create_scheduler
from reminder_bot.handlers.common import router as common_router
from reminder_bot.handlers.confirmation import setup_confirmation_handlers

logging.basicConfig(level=logging.INFO)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    rm = ReminderManager(bot, None)  # scheduler injected later
    scheduler = create_scheduler(EVENTS, rm)
    rm.scheduler = scheduler  # circular but harmless

    # Routers
    setup_confirmation_handlers(dp, rm)
    dp.include_router(common_router)

    scheduler.start()
    logging.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
