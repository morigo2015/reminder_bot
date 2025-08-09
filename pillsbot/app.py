from __future__ import annotations

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import config as cfg
from .core.reminder_engine import ReminderEngine
from .adapters.telegram_adapter import TelegramAdapter

async def main() -> None:
    cfg.validate()
    token = cfg.get_bot_token()

    engine = ReminderEngine(cfg, adapter=None)  # temporary None to build adapter
    adapter = TelegramAdapter(token, engine, [p["group_id"] for p in cfg.PATIENTS])
    # back-reference
    engine.adapter = adapter

    scheduler = AsyncIOScheduler(timezone=cfg.TZ)
    await engine.start(scheduler)
    scheduler.start()

    # Run polling forever
    await adapter.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
