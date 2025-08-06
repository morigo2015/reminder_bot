import os
import sys
import asyncio
import logging
import yaml
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config.dialogs import setup as setup_config
from dialogues.med import med_router
from dialogues.pressure import pressure_router
from dialogues.status import status_router
from services.scheduler import SchedulerService

API_TOKEN = os.getenv("BOT_TOKEN")
PATIENT_CHAT_ID = os.getenv("PATIENT_CHAT_ID")
NURSE_CHAT_ID = os.getenv("NURSE_CHAT_ID")

async def load_config():
    with open("config/dialogs.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

async def main():
    logging.basicConfig(level=logging.INFO)
    if not API_TOKEN or not PATIENT_CHAT_ID or not NURSE_CHAT_ID:
        logging.error("BOT_TOKEN, PATIENT_CHAT_ID, and NURSE_CHAT_ID must be set")
        sys.exit(1)
    config = await load_config()
    setup_config(config)
    bot = Bot(token=API_TOKEN, parse_mode="HTML")
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(med_router)
    dp.include_router(pressure_router)
    dp.include_router(status_router)
    scheduler = SchedulerService(dp, bot, config, int(PATIENT_CHAT_ID), int(NURSE_CHAT_ID))
    scheduler.setup_jobs()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
