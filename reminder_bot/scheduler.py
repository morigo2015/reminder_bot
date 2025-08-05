"""APScheduler initialisation + event & utility job registration."""

from __future__ import annotations
from typing import List, Set  # , Dict,
# from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from reminder_bot.models import Event
from reminder_bot.services.reminder_manager import ReminderManager
from reminder_bot.config.dialogs_loader import DIALOGS
from reminder_bot.handlers.pressure import _PRESSURE_STATE
from reminder_bot.models import PressureDayState


def _schedule_events(
    scheduler: AsyncIOScheduler, events: List[Event], rm: ReminderManager
):
    for ev in events:
        scheduler.add_job(
            rm.trigger_event,
            trigger=CronTrigger(**ev.scheduler_args, timezone="Europe/Kyiv"),
            id=f"{ev.chat_id}:{ev.event_name}",
            args=[ev],
            replace_existing=True,
        )


def _schedule_pressure_reminder(
    scheduler: AsyncIOScheduler,
    bot,
    pressure_message: str,
    remind_hour: int,
    patient_chat_ids: Set[int],
):
    async def _pressure_job():
        for chat_id in patient_chat_ids:
            st = _PRESSURE_STATE.setdefault(chat_id, PressureDayState())
            st.reset_if_new_day()
            if not st.received:
                await bot.send_message(chat_id, pressure_message)

    scheduler.add_job(
        _pressure_job,
        trigger=CronTrigger(hour=remind_hour, minute=0, timezone="Europe/Kyiv"),
        id="daily_pressure_reminder",
        replace_existing=True,
    )


def create_scheduler(events: List[Event], rm: ReminderManager, bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    _schedule_events(scheduler, events, rm)
    pm = DIALOGS["messages"]["pressure"]["daily_reminder"]
    remind_hour = DIALOGS["timings"]["pressure_remind_hour"]
    patient_chat_ids = {ev.chat_id for ev in events}
    _schedule_pressure_reminder(scheduler, bot, pm, remind_hour, patient_chat_ids)
    return scheduler
