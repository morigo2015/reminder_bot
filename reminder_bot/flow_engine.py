# flow_engine.py

import logging
from apscheduler.triggers.cron import CronTrigger

from config.dialogs_loader import DIALOGS
from services.reminder_manager import ReminderManager

logger = logging.getLogger(__name__)


class FlowEngine:
    """
    Schedules all reminder flows defined in config/dialogs_config.yaml.
    """

    def __init__(self, bot, dispatcher, scheduler, log_service):
        """
        :param bot: Aiogram Bot instance
        :param dispatcher: Aiogram Dispatcher instance
        :param scheduler: APScheduler AsyncIOScheduler instance
        :param log_service: logging adapter (e.g. CSV or DB)
        """
        self.bot = bot
        self.dispatcher = dispatcher
        self.scheduler = scheduler
        self.manager = ReminderManager(bot, dispatcher, scheduler, log_service)

    def start(self):
        """
        Schedule every event under DIALOGS as a cron job.
        The scheduler itself is started in bot.py.
        """
        for event_name, cfg in DIALOGS.items():
            trigger_spec = cfg.get("trigger", "")
            if not trigger_spec.startswith("cron:"):
                logger.warning(
                    f"[FLOW ENGINE] Unsupported trigger '{trigger_spec}' for '{event_name}'"
                )
                continue

            try:
                _, spec = trigger_spec.split(":", 1)
                hour_str, minute_str = spec.strip().split()
                hour, minute = int(hour_str), int(minute_str)
            except Exception as e:
                logger.error(f"[FLOW ENGINE] Invalid cron spec for '{event_name}': {e}")
                continue

            chat_id = cfg["chat_id"]
            user_id = chat_id  # private chats

            trigger = CronTrigger(
                hour=hour, minute=minute, timezone=self.scheduler.timezone
            )
            job_id = f"reminder_{event_name}"

            logger.debug(
                f"[FLOW ENGINE] Scheduling '{event_name}' ({job_id}) at {hour:02d}:{minute:02d} for chat {chat_id}"
            )

            self.scheduler.add_job(
                self.manager.start_flow,
                trigger=trigger,
                kwargs={"event_name": event_name, "user_id": user_id},
                id=job_id,
                replace_existing=True,
            )

        logger.info("[FLOW ENGINE] All jobs scheduled")
