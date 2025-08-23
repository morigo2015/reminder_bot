# app/main.py
import asyncio
from contextlib import suppress
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app import config
from app.db.pool import init_pool
from app.bot.handlers import router
from app.logic import ticker, sweeper
from app.db.patients import upsert_patient


async def main():
    await init_pool()

    # Seed patients so FKs are satisfied
    for p in config.PATIENTS:
        await upsert_patient(p["id"], p["chat_id"], p["name"])

    bot = Bot(
        token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(router)

    # Use the loop helpers already in your repo
    t1 = asyncio.create_task(ticker_loop(bot))  # <— defined below
    t2 = asyncio.create_task(sweeper_loop(bot))  # <— defined below

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
            await ticker.tick(bot)  # tick exists
        except Exception as e:
            print({"level": "error", "action": "ticker", "exception": str(e)})
        await asyncio.sleep(config.TICK_SECONDS)


async def sweeper_loop(bot: Bot):
    while True:
        try:
            await sweeper.sweep(bot)  # sweep exists
        except Exception as e:
            print({"level": "error", "action": "sweeper", "exception": str(e)})
        await asyncio.sleep(config.SWEEP_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
