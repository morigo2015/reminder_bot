import logging
from apscheduler.triggers.cron import CronTrigger
from config.dialogs_loader import DIALOGS
from services.reminder_manager import ReminderManager

logger = logging.getLogger(__name__)


class FlowEngine:
    def __init__(self, scheduler, reminder_manager: ReminderManager):
        self.scheduler = scheduler
        self.reminder_manager = reminder_manager

    def schedule_events(self):
        for event_name, cfg in DIALOGS.items():
            trigger_spec = cfg["trigger"]
            if trigger_spec.startswith("cron:"):
                try:
                    # Expect "cron: HH MM"
                    _, spec = trigger_spec.split(":", 1)
                    hour_str, minute_str = spec.strip().split()
                    hour, minute = int(hour_str), int(minute_str)

                    trigger = CronTrigger(
                        hour=hour, minute=minute, timezone=self.scheduler.timezone
                    )
                    job_id = f"reminder_{event_name}"
                    logger.debug(
                        f"[FLOW ENGINE] Scheduling '{event_name}' ({job_id}) at {hour:02d}:{minute:02d}"
                    )
                    self.scheduler.add_job(
                        self.reminder_manager.start_flow,
                        trigger=trigger,
                        args=[event_name],
                        id=job_id,
                        replace_existing=True,
                    )
                    job = self.scheduler.get_job(job_id)
                    logger.debug(
                        f"[FLOW ENGINE] → next run for {job_id!r}: {job.next_run_time}"
                    )
                except Exception as e:
                    logger.error(
                        f"[FLOW ENGINE] Invalid cron spec for '{event_name}': {e}"
                    )
            else:
                logger.warning(
                    f"[FLOW ENGINE] Unsupported trigger '{trigger_spec}' for '{event_name}'"
                )
