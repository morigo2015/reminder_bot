import os
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from services.scheduler import init_scheduler
from dialogues.med import router as med_router
from dialogues.pressure import router as pressure_router
from dialogues.status import router as status_router

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher(storage=MemoryStorage())

    # Initialize scheduler
    init_scheduler(dp)

    # Include routers
    dp.include_router(med_router)
    dp.include_router(pressure_router)
    dp.include_router(status_router)

    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
