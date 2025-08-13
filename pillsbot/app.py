# pillsbot/app.py
from __future__ import annotations

import sys
from pathlib import Path
import asyncio
import logging

# --------------------------------------------------------------------------------------
# Ensure project root is in sys.path so "import pillsbot.*" always works
# --------------------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as cfg  # noqa: E402
from config import get_bot_token, PATIENTS  # noqa: E402
from pillsbot.core.reminder_engine import ReminderEngine  # noqa: E402
from pillsbot.adapters.telegram_adapter import TelegramAdapter  # noqa: E402
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: E402


async def schedule_jobs(engine: ReminderEngine, timezone) -> AsyncIOScheduler:
    """
    Schedule daily dose reminders and measurement checks at exact times from config.
    """
    sched = AsyncIOScheduler(timezone=timezone)

    # Doses
    for p in PATIENTS:
        pid = p["patient_id"]
        for d in p["doses"]:
            hh, mm = (int(x) for x in d["time"].split(":"))
            sched.add_job(
                engine._start_dose_job,
                trigger="cron",
                hour=hh,
                minute=mm,
                kwargs={"patient_id": pid, "time_str": d["time"]},
                id=f"dose:{pid}:{d['time']}",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=300,
                max_instances=1,
            )

    # Daily measurement checks
    for p in PATIENTS:
        pid = p["patient_id"]
        for chk in p.get("measurement_checks", []):
            hh, mm = (int(x) for x in chk["time"].split(":"))
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
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
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

    # Initialize engine state
    await engine.start(scheduler=None)

    # Proper time-based scheduling
    await schedule_jobs(engine, timezone=cfg.TZ)

    log.info("startup.ready " + f"patients={len(PATIENTS)}")

    # Single polling loop
    await adapter.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
