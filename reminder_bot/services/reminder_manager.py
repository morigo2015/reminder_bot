# services/reminder_manager.py

import logging
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.fsm.storage.base import StorageKey

from config.dialogs_loader import DIALOGS
from states import ReminderStates

logger = logging.getLogger(__name__)


class ReminderManager:
    def __init__(self, bot: Bot, dispatcher, scheduler, log_service):
        self.bot = bot
        self.dp = dispatcher
        self.storage = dispatcher.storage
        self.scheduler = scheduler
        self.log = log_service

    def _make_key(self, chat_id: int, user_id: int) -> StorageKey:
        return StorageKey(chat_id, user_id, str(self.bot.id))

    async def start_flow(self, event_name: str, user_id: int):
        cfg = DIALOGS[event_name]
        chat_id = cfg["chat_id"]

        await self.bot.send_message(chat_id, cfg["main_text"])
        logger.debug(f"[REMINDER] Sent '{event_name}' to chat {chat_id}")

        key = self._make_key(chat_id, user_id)
        await self.storage.set_state(key, ReminderStates.waiting_confirmation)
        await self.storage.update_data(
            key,
            {
                "event": event_name,
                "attempts": 0,
                "clarifications": 0,
                "confirmed": False,
            },
        )

        retries = cfg.get("retries", 0)
        delay = cfg.get("retry_delay_seconds", 0)
        if retries and delay:
            await self._schedule_retry(
                event_name, chat_id, user_id, attempt=1, delay=delay
            )

    async def _schedule_retry(
        self, event_name: str, chat_id: int, user_id: int, attempt: int, delay: int
    ):
        next_run = datetime.now(self.scheduler.timezone) + timedelta(seconds=delay)
        job_id = f"retry_{event_name}_{chat_id}_{user_id}_{attempt}"
        logger.debug(f"[RETRY] #{attempt} for '{event_name}' at {next_run}")

        self.scheduler.add_job(
            self._handle_retry,
            trigger="date",
            run_date=next_run,
            kwargs={
                "event_name": event_name,
                "chat_id": chat_id,
                "user_id": user_id,
                "attempt": attempt,
            },
            id=job_id,
            replace_existing=True,
        )

    async def _handle_retry(
        self, event_name: str, chat_id: int, user_id: int, attempt: int
    ):
        key = self._make_key(chat_id, user_id)
        data = await self.storage.get_data(key)
        if data.get("confirmed"):
            return

        cfg = DIALOGS[event_name]
        await self.bot.send_message(chat_id, cfg["retry_text"])
        logger.debug(f"[RETRY] Fired #{attempt} for '{event_name}'")

        await self.storage.update_data(key, {"attempts": attempt})

        max_retries = cfg.get("retries", 0)
        delay = cfg.get("retry_delay_seconds", 0)
        if attempt < max_retries:
            await self._schedule_retry(event_name, chat_id, user_id, attempt + 1, delay)
        else:
            await self._start_clarification(event_name, chat_id, user_id)

    async def _start_clarification(self, event_name: str, chat_id: int, user_id: int):
        cfg = DIALOGS[event_name]
        await self.bot.send_message(
            chat_id, cfg.get("clarify_text", "Please confirm (OK)")
        )
        logger.debug(f"[CLARIFY] for '{event_name}'")

        key = self._make_key(chat_id, user_id)
        await self.storage.set_state(key, ReminderStates.waiting_clarification)
        await self.storage.update_data(key, {"clarifications": 1})

    async def cancel_flow(self, event_name: str, chat_id: int, user_id: int):
        prefix = f"{event_name}_{chat_id}_{user_id}"
        for job in self.scheduler.get_jobs():
            if prefix in job.id:
                job.remove()

        key = self._make_key(chat_id, user_id)
        data = await self.storage.get_data(key)
        await self.log.confirmation(
            chat_id=chat_id,
            event=event_name,
            status="confirmed",
            attempts=data.get("attempts", 0),
            clarifications=data.get("clarifications", 0),
        )
        await self.storage.reset_state(key)

    async def finalize_flow(self, event_name: str, chat_id: int, user_id: int):
        prefix = f"{event_name}_{chat_id}_{user_id}"
        for job in self.scheduler.get_jobs():
            if prefix in job.id:
                job.remove()

        key = self._make_key(chat_id, user_id)
        data = await self.storage.get_data(key)
        await self.log.confirmation(
            chat_id=chat_id,
            event=event_name,
            status="clarified",
            attempts=data.get("attempts", 0),
            clarifications=data.get("clarifications", 0),
        )
        await self.storage.reset_state(key)
