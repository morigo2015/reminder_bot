# pillsbot/app.py
from __future__ import annotations

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pillsbot import config as cfg
from pillsbot.core.config_validation import validate_config
from pillsbot.core.reminder_engine import ReminderEngine
from pillsbot.adapters.telegram_adapter import TelegramAdapter
from pillsbot.core.logging_utils import setup_logging, kv


async def main() -> None:
    # Validate configuration before starting anything
    validate_config(cfg)

    # Setup logging (separate audit file, console mirror)
    setup_logging(cfg)
    log = logging.getLogger("pillsbot.app")

    token = cfg.get_bot_token()

    engine = ReminderEngine(cfg, adapter=None)  # temporary None to build adapter
    adapter = TelegramAdapter(token, engine, [p["group_id"] for p in cfg.PATIENTS])
    engine.adapter = adapter

    scheduler = AsyncIOScheduler(timezone=cfg.TZ)

    # startup.* must be INFO
    log.info("startup.begin " + kv(timezone=cfg.TIMEZONE))
    await engine.start(scheduler)
    scheduler.start()
    log.info("startup.ready " + kv(patients=len(cfg.PATIENTS)))

    # Not startup, not messaging → DEBUG
    log.debug("polling.start")
    await adapter.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
