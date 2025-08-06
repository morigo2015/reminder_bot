import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import (
    EVENT_JOB_ADDED,
    EVENT_JOB_SUBMITTED,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
)

from config.config import BOT_TOKEN
from handlers.confirmation import router as confirmation_router
from handlers.pressure import router as pressure_router
from handlers.health_status import router as status_router
from services.log_service import LogService
from services.reminder_manager import ReminderManager
from flow_engine import FlowEngine

# ——— Logger setup —————————————————————————————————————————————————————————
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ——— Bot, Dispatcher, Scheduler ————————————————————————————————————————————
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")


def _log_scheduler_event(event):
    job = scheduler.get_job(event.job_id)
    if event.code == EVENT_JOB_ADDED:
        logger.debug(
            f"[SCHEDULER] Added job {event.job_id!r}: next run at {job.next_run_time}"
        )
    elif event.code == EVENT_JOB_SUBMITTED:
        logger.debug(f"[SCHEDULER] Job {event.job_id!r} submitted to executor")
    elif event.code == EVENT_JOB_EXECUTED:
        logger.debug(f"[SCHEDULER] Job {event.job_id!r} executed successfully")
    elif event.code == EVENT_JOB_ERROR:
        logger.error(
            f"[SCHEDULER] Job {event.job_id!r} raised error: {event.exception!r}"
        )


async def main():
    # Attach debug listener
    scheduler.add_listener(
        _log_scheduler_event,
        EVENT_JOB_ADDED | EVENT_JOB_SUBMITTED | EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
    )
    scheduler.start()

    # Init services
    log_service = LogService()
    manager = ReminderManager(bot, dp, scheduler, log_service)

    dp["log_service"] = log_service
    dp["reminder_manager"] = manager

    # Register Telegram handlers
    dp.include_router(confirmation_router)
    dp.include_router(pressure_router)
    dp.include_router(status_router)

    # Schedule flows from YAML
    flow = FlowEngine(scheduler, manager)
    flow.schedule_events()

    # Log all scheduled jobs at startup
    for job in scheduler.get_jobs():
        logger.info(
            f"[SCHEDULER STARTUP] Job {job.id!r}: trigger={job.trigger!r}, next_run={job.next_run_time}"
        )

    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
