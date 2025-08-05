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

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    # Initialize bot with default properties
    default_props = DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    bot = Bot(token=BOT_TOKEN, default=default_props)
    dp = Dispatcher()

    # Reminder manager
    rm = ReminderManager(bot, None)

    # Setup handlers
    setup_confirmation_handlers(dp, rm)
    dp.include_router(common_router)

    # Create and start scheduler (pass bot to scheduler)
    scheduler = create_scheduler(EVENTS, rm, bot)
    rm.scheduler = scheduler
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    # Debug: list all scheduled jobs
    for job in scheduler.get_jobs():
        logger.debug(
            "Scheduled job -> id: %s | next_run: %s | trigger: %s | args: %s",
            job.id,
            job.next_run_time,
            type(job.trigger).__name__,
            job.args,
        )

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
