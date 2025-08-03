"""Central coordination of triggers, retries, and confirmations."""

from __future__ import annotations
from typing import Dict, Tuple
from datetime import timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..models import Event, RuntimeState
from ..utils import logging as log
from ..utils.time import kyiv_now
from . import escalation

_STATE: Dict[Tuple[int, str], RuntimeState] = {}


def _key(chat_id: int, event_name: str) -> Tuple[int, str]:
    return chat_id, event_name


class ReminderManager:
    def __init__(self, bot: Bot, scheduler: AsyncIOScheduler | None):
        self.bot = bot
        self.scheduler = scheduler

    async def trigger_event(self, event: Event) -> None:
        """Send initial reminder and schedule retries if needed."""
        state = _STATE.setdefault(_key(event.chat_id, event.event_name), RuntimeState())
        state.attempt = 0
        state.confirmed = False
        await self.bot.send_message(event.chat_id, event.main_message)
        if event.retries > 0 and self.scheduler:
            self._schedule_retry(event)

    def _schedule_retry(self, event: Event) -> None:
        """Schedule a one-off retry at Kyiv now + retry_delay."""
        state = _STATE[_key(event.chat_id, event.event_name)]
        run_date = kyiv_now() + timedelta(seconds=event.retry_delay_seconds)
        job = self.scheduler.add_job(
            self.handle_retry, "date", args=[event], run_date=run_date
        )
        state.retry_job_id = job.id

    async def handle_retry(self, event: Event) -> None:
        """Send retry messages and escalate after final retry."""
        state = _STATE.get(_key(event.chat_id, event.event_name))
        # If already confirmed or no state, nothing to do
        if not state or state.confirmed:
            return
        # Increment attempt count
        state.attempt += 1
        # Send retry message if within retry limit
        if state.attempt <= event.retries:
            await self.bot.send_message(event.chat_id, event.retry_message)
        # Decide next steps: schedule next retry or escalate
        if state.attempt < event.retries and self.scheduler:
            # Schedule the next retry
            self._schedule_retry(event)
        else:
            # Retries exhausted: log failure and escalate
            log.log(event.event_name, event.chat_id, "FAILED", state.attempt)
            if event.escalate:
                await escalation.escalate(self.bot, event.event_name, event.chat_id)

    def mark_confirmed(self, chat_id: int, event_name: str) -> None:
        """Mark an event confirmed and cancel further retries."""
        state = _STATE.get(_key(chat_id, event_name))
        if not state or state.confirmed:
            return
        state.confirmed = True
        # Cancel pending retry job if any
        if state.retry_job_id and self.scheduler:
            try:
                self.scheduler.remove_job(state.retry_job_id)
            except Exception:
                pass
        # Log the confirmation
        log.log(event_name, chat_id, "CONFIRMED", state.attempt)
