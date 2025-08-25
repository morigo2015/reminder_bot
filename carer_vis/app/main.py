# app/main.py
import asyncio
import logging
from contextlib import suppress
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app import config
from app.bot.handlers import router
from app.logic import ticker, sweeper
from app.db.patients import upsert_patient
from app.db.pills import delete_today_records
from app.util import timez


async def main():
    # Configure logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Seed patients so FKs are satisfied (SQLAlchemy engine is lazy-initialized)
    for p in config.PATIENTS:
        await upsert_patient(p["id"], p["chat_id"], p["name"])
    
    # Clean up today's pill records for fresh reminders
    today = timez.date_kyiv()
    total_deleted = 0
    for patient in config.PATIENTS:
        pill_cfg = patient.get("pills", {}) or {}
        times = pill_cfg.get("times", {})
        for dose in times.keys():
            deleted = await delete_today_records(patient["id"], today, dose)
            total_deleted += deleted
            if deleted > 0:
                logging.debug("Cleaned up %d records for patient=%s dose=%s date=%s", 
                            deleted, patient["id"], dose, today)
    
    if total_deleted > 0:
        logging.info("Bot startup: cleaned %d pill records for today=%s", total_deleted, today)

    bot = Bot(
        token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(router)

    t1 = asyncio.create_task(ticker_loop(bot))
    t2 = asyncio.create_task(sweeper_loop(bot))

    try:
        await dp.start_polling(bot)
    finally:
        for t in (t1, t2):
            t.cancel()
            with suppress(asyncio.CancelledError):
                await t
        await bot.session.close()


async def ticker_loop(bot: Bot):
    while True:
        try:
            await ticker.tick(bot)
        except Exception as e:
            print({"level": "error", "action": "ticker", "exception": str(e)})
        await asyncio.sleep(config.TICK_SECONDS)


async def sweeper_loop(bot: Bot):
    while True:
        try:
            await sweeper.sweep(bot)
        except Exception as e:
            print({"level": "error", "action": "sweeper", "exception": str(e)})
        await asyncio.sleep(config.SWEEP_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
