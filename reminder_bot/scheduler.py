"""APScheduler initialisation + event registration."""
from typing import List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .models import Event
from .services.reminder_manager import ReminderManager

def create_scheduler(events: List[Event], rm: ReminderManager) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    for ev in events:
        scheduler.add_job(
            rm.trigger_event,
            trigger=CronTrigger(**ev.scheduler_args, timezone="Europe/Kyiv"),
            id=f"{ev.chat_id}:{ev.event_name}",
            args=[ev],
            replace_existing=True
        )
    return scheduler
