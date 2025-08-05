"""Central coordination of triggers, retries, and confirmations with debug logging."""

from __future__ import annotations
from typing import Dict, Tuple
from datetime import timedelta

import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..models import Event, RuntimeState
from ..utils.time import kyiv_now
from ..utils import logging as log
from . import escalation

_STATE: Dict[Tuple[int, str], RuntimeState] = {}
logger = logging.getLogger(__name__)

def _key(chat_id: int, event_name: str) -> Tuple[int, str]:
    return chat_id, event_name

class ReminderManager:
    def __init__(self, bot: Bot, scheduler: AsyncIOScheduler | None):
        self.bot = bot
        self.scheduler = scheduler

    async def trigger_event(self, event: Event) -> None:
        now = kyiv_now()
        logger.debug(
            "Triggering event '%s' for chat %s at %s; scheduler_args=%s",
            event.event_name,
            event.chat_id,
            now,
            event.scheduler_args,
        )
        state = _STATE.setdefault(_key(event.chat_id, event.event_name), RuntimeState())
        state.attempt = 0
        state.confirmed = False

        await self.bot.send_message(event.chat_id, event.main_text)

        if event.retries > 0 and self.scheduler:
            self._schedule_retry(event)

    def _schedule_retry(self, event: Event) -> None:
        state = _STATE[_key(event.chat_id, event.event_name)]
        run_date = kyiv_now() + timedelta(seconds=event.retry_delay_seconds)
        job = self.scheduler.add_job(
            self.handle_retry, "date", args=[event], run_date=run_date
        )
        state.retry_job_id = job.id
        logger.debug(
            "Scheduled retry for event '%s' chat %s at %s | job_id=%s",
            event.event_name,
            event.chat_id,
            run_date,
            job.id,
        )

    async def handle_retry(self, event: Event) -> None:
        state = _STATE.get(_key(event.chat_id, event.event_name))
        if not state or state.confirmed:
            logger.debug(
                "Skipping retry for event '%s' chat %s: no state or already confirmed",
                event.event_name, event.chat_id
            )
            return

        state.attempt += 1
        logger.debug(
            "Retry attempt %d for event '%s' chat %s",
            state.attempt, event.event_name, event.chat_id
        )

        if state.attempt <= event.retries:
            logger.debug(
                "Sending retry message for event '%s' chat %s | attempt %d",
                event.event_name, event.chat_id, state.attempt
            )
            await self.bot.send_message(event.chat_id, event.retry_text)

        if state.attempt < event.retries and self.scheduler:
            logger.debug(
                "Rescheduling next retry for event '%s' chat %s",
                event.event_name, event.chat_id
            )
            self._schedule_retry(event)
        else:
            logger.debug(
                "Retries exhausted for event '%s' chat %s; logging failure and escalating",
                event.event_name, event.chat_id
            )
            log.log(event.event_name, event.chat_id, "FAILED", state.attempt)
            if event.escalate:
                await escalation.escalate(self.bot, event.event_name, event.chat_id, state.attempt)

    def mark_confirmed(self, chat_id: int, event_name: str) -> None:
        state = _STATE.get(_key(chat_id, event_name))
        if not state or state.confirmed:
            logger.debug(
                "Received confirmation for event '%s' chat %s but no pending state",
                event_name, chat_id
            )
            return

        state.confirmed = True
        if state.retry_job_id and self.scheduler:
            try:
                self.scheduler.remove_job(state.retry_job_id)
                logger.debug(
                    "Cancelled retry job %s for event '%s' chat %s",
                    state.retry_job_id, event_name, chat_id
                )
            except Exception as e:
                logger.debug(
                    "Error cancelling retry job %s: %s",
                    state.retry_job_id, e
                )
        log.log(event_name, chat_id, "CONFIRMED", state.attempt)
        logger.debug(
            "Event '%s' chat %s confirmed at attempt %d",
            event_name, chat_id, state.attempt
        )