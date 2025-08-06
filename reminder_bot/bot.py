import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from reminder_bot.flow_engine import FlowEngine
from reminder_bot.services.log_service import LogService
from reminder_bot.services.reminder_manager import ReminderManager
from reminder_bot.handlers.confirmation import router as confirmation_router
from reminder_bot.handlers.pressure import router as pressure_router
from reminder_bot.handlers.health_status import router as status_router

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def main():
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    log_service = LogService()
    manager = ReminderManager(bot, dp, scheduler, log_service)

    # Store services in dispatcher context
    dp["log_service"] = log_service
    dp["reminder_manager"] = manager

    # Register handlers
    dp.include_router(confirmation_router)
    dp.include_router(pressure_router)
    dp.include_router(status_router)

    # Schedule flows from YAML
    flow = FlowEngine(scheduler, manager)
    flow.schedule_events()

    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
