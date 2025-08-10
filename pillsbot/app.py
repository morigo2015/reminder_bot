# pillsbot/app.py
from __future__ import annotations

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pillsbot import config as cfg
from pillsbot.core.config_validation import validate_config
from pillsbot.core.reminder_engine import ReminderEngine
from pillsbot.adapters.telegram_adapter import TelegramAdapter


async def main() -> None:
    # Validate configuration before starting anything
    validate_config(cfg)

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
