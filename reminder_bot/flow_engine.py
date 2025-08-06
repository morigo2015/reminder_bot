from apscheduler.triggers.cron import CronTrigger
from reminder_bot.config.dialogs_loader import DIALOGS


class FlowEngine:
    def __init__(self, scheduler, reminder_manager):
        self.scheduler = scheduler
        self.reminder_manager = reminder_manager

    def schedule_events(self):
        for event_name, cfg in DIALOGS["events"].items():
            trigger_spec = cfg.get("trigger")
            if not trigger_spec:
                print(f"⚠️ Skipping event '{event_name}': no trigger spec defined.")
                continue
            if trigger_spec.startswith("cron:"):
                try:
                    spec = trigger_spec.split(":", 1)[1].strip()
                    hour, minute = map(int, spec.split())
                    trigger = CronTrigger(
                        hour=hour, minute=minute, timezone=self.scheduler.timezone
                    )
                    job_id = f"reminder_{event_name}"
                    self.scheduler.add_job(
                        self.reminder_manager.start_flow,
                        trigger,
                        args=[event_name],
                        id=job_id,
                    )
                except Exception as e:
                    print(f"❌ Invalid cron spec for '{event_name}': {e}")
            else:
                print(
                    f"⚠️ Skipping event '{event_name}': unsupported trigger spec '{trigger_spec}'"
                )
