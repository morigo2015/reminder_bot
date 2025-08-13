# pillsbot/app.py
from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

import config as cfg
from config import get_bot_token, PATIENTS

from pillsbot.core.reminder_engine import ReminderEngine
from pillsbot.adapters.telegram_adapter import TelegramAdapter

from apscheduler.schedulers.asyncio import AsyncIOScheduler


async def schedule_jobs(engine: ReminderEngine, timezone: ZoneInfo) -> AsyncIOScheduler:
    """
    Schedule daily dose reminders and measurement checks at exact times from config.
    Uses a single AsyncIOScheduler instance (no immediate firing).
    """
    sched = AsyncIOScheduler(timezone=timezone)

    # Doses
    for p in PATIENTS:
        pid = p["patient_id"]
        for d in p["doses"]:
            t = d["time"]  # "HH:MM"
            hh, mm = (int(x) for x in t.split(":"))
            sched.add_job(
                engine._start_dose_job,  # coroutine supported by AsyncIOScheduler
                trigger="cron",
                hour=hh,
                minute=mm,
                kwargs={"patient_id": pid, "time_str": t},
                id=f"dose:{pid}:{t}",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=300,
                max_instances=1,
            )

    # Daily measurement checks
    for p in PATIENTS:
        pid = p["patient_id"]
        for chk in p.get("measurement_checks", []):
            t = chk["time"]
            hh, mm = (int(x) for x in t.split(":"))
            sched.add_job(
                engine._job_measure_check,
                trigger="cron",
                hour=hh,
                minute=mm,
                kwargs={"patient_id": pid, "measure_id": chk["measure_id"]},
                id=f"measure:{pid}:{chk['measure_id']}",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=300,
                max_instances=1,
            )

    sched.start()
    return sched


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s"
    )
    log = logging.getLogger("pillsbot.app")
    log.info("startup.begin " + f"timezone='{cfg.TIMEZONE}'")

    # Build engine FIRST with adapter=None to break circular dependency
    engine = ReminderEngine(cfg, adapter=None)

    # Build Telegram adapter and attach back to the engine
    bot_token = get_bot_token()
    patient_groups = [p["group_id"] for p in PATIENTS]
    adapter = TelegramAdapter(bot_token, engine=engine, patient_groups=patient_groups)
    engine.attach_adapter(adapter)

    # Initialize engine state, but DO NOT pass a scheduler here — we schedule explicitly below
    await engine.start(scheduler=None)

    # Proper time-based scheduling (no immediate job runs)
    _sched = await schedule_jobs(engine, timezone=cfg.TZ)

    log.info("startup.ready " + f"patients={len(PATIENTS)}")

    # Run a single polling loop for this process
    await adapter.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
