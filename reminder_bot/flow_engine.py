from apscheduler.triggers.cron import CronTrigger
from reminder_bot.config.dialogs_loader import DIALOGS

class FlowEngine:
    def __init__(self, scheduler, reminder_manager):
        self.scheduler = scheduler
        self.reminder_manager = reminder_manager

    def schedule_events(self):
        for event_name, cfg in DIALOGS['events'].items():
            trigger_spec = cfg.get('trigger')  # e.g. 'cron:0 2:45'
            if trigger_spec and trigger_spec.startswith('cron:'):
                spec = trigger_spec.split(':',1)[1].strip()
                hour, minute = map(int, spec.split())
                trigger = CronTrigger(hour=hour, minute=minute,
                                      timezone=self.scheduler.timezone)
                job_id = f"reminder_{event_name}"
                # pass event_name and chat_id via args
                self.scheduler.add_job(self.reminder_manager.start_flow,
                                       trigger, args=[event_name],
                                       id=job_id)
            else:
                raise ValueError(f"Unsupported trigger spec: {trigger_spec}")
