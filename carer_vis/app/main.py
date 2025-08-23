from __future__ import annotations
import asyncio
import signal
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from app import config
from app.db.pool import init_pool
from app.bot.handlers import router
from app.logic import ticker, sweeper
from app.util.timez import now_kyiv


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


async def main():
    await init_pool()

    bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(router)

    # background loops
    t1 = asyncio.create_task(ticker_loop(bot))
    t2 = asyncio.create_task(sweeper_loop(bot))

    # shutdown signals
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, dp.stop_polling)
        except NotImplementedError:
            pass

    try:
        await dp.start_polling(bot)
    finally:
        t1.cancel(); t2.cancel()
        with contextlib.suppress(Exception):
            await bot.session.close()


if __name__ == "__main__":
    import contextlib
    asyncio.run(main())
