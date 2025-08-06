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

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _make_key(self, chat_id: int, user_id: int) -> StorageKey:
        # bot_id must be str
        return StorageKey(chat_id, user_id, str(self.bot.id))

    # ---------------------------------------------------------------------
    # Public API – called from FlowEngine
    # ---------------------------------------------------------------------
    async def start_flow(self, event_name: str):
        cfg = DIALOGS[event_name]
        chat_id = cfg["chat_id"]

        await self.bot.send_message(chat_id, cfg["main_text"])
        logger.debug(f"[REMINDER] Sent main_text for '{event_name}' to chat {chat_id}")

        key = self._make_key(chat_id, chat_id)
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
        if retries > 0 and delay > 0:
            await self._schedule_retry(event_name, chat_id, attempt=1, delay=delay)

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    async def _schedule_retry(
        self, event_name: str, chat_id: int, attempt: int, delay: int
    ):
        next_run = datetime.now(self.scheduler.timezone) + timedelta(seconds=delay)
        job_id = f"retry_{event_name}_{chat_id}_{attempt}"
        logger.debug(
            f"[RETRY] Scheduling retry #{attempt} for '{event_name}' at {next_run} (id={job_id})"
        )

        self.scheduler.add_job(
            self._handle_retry,
            trigger="date",
            run_date=next_run,
            kwargs={"event_name": event_name, "chat_id": chat_id, "attempt": attempt},
            id=job_id,
            replace_existing=True,
        )

    async def _handle_retry(self, event_name: str, chat_id: int, attempt: int):
        key = self._make_key(chat_id, chat_id)
        data = await self.storage.get_data(key)
        if data.get("confirmed"):
            logger.debug(f"[RETRY] '{event_name}' already confirmed; skipping retry.")
            return

        cfg = DIALOGS[event_name]
        await self.bot.send_message(chat_id, cfg["retry_text"])
        logger.debug(
            f"[REMINDER] Fired retry #{attempt} for '{event_name}' to chat {chat_id}"
        )

        await self.storage.update_data(key, {"attempts": attempt})

        max_retries = cfg.get("retries", 0)
        delay = cfg.get("retry_delay_seconds", 0)

        if attempt < max_retries:
            await self._schedule_retry(event_name, chat_id, attempt + 1, delay)
        else:
            await self._start_clarification(event_name, chat_id)

    async def _start_clarification(self, event_name: str, chat_id: int):
        cfg = DIALOGS[event_name]
        await self.bot.send_message(
            chat_id, cfg.get("clarify_text", "Please confirm (OK)")
        )
        logger.debug(
            f"[CLARIFY] Starting clarification for '{event_name}' to chat {chat_id}"
        )

        key = self._make_key(chat_id, chat_id)
        await self.storage.set_state(key, ReminderStates.waiting_clarification)
        await self.storage.update_data(key, {"clarifications": 1})

    # ---------------------------------------------------------------------
    # Flow-ending helpers, called from handlers
    # ---------------------------------------------------------------------
    async def _clean_jobs(self, event_name: str, chat_id: int):
        for job in list(self.scheduler.get_jobs()):
            if job.id.startswith(f"retry_{event_name}_{chat_id}") or job.id.startswith(
                f"clarify_{event_name}_{chat_id}"
            ):
                job.remove()
                logger.debug(f"[CLEAN] Removed job {job.id!r}")

    async def cancel_flow(self, event_name: str, chat_id: int):
        await self._clean_jobs(event_name, chat_id)

        key = self._make_key(chat_id, chat_id)
        data = await self.storage.get_data(key)
        await self.log.confirmation(
            chat_id=chat_id,
            event_name=event_name,
            status="confirmed",
            attempts=data.get("attempts", 0),
            clarifications=data.get("clarifications", 0),
        )
        await self.storage.reset_state(key)

    async def finalize_flow(self, event_name: str, chat_id: int):
        await self._clean_jobs(event_name, chat_id)

        key = self._make_key(chat_id, chat_id)
        data = await self.storage.get_data(key)
        await self.log.confirmation(
            chat_id=chat_id,
            event_name=event_name,
            status="clarified",
            attempts=data.get("attempts", 0),
            clarifications=data.get("clarifications", 0),
        )
        await self.storage.reset_state(key)
