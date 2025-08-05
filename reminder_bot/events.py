"""Static list of Event definitions (schedule only).
Human‑facing texts and retry delays are loaded from dialogs_config.yaml."""

from reminder_bot.models import Event
from reminder_bot.config.dialogs_loader import DIALOGS

# Replace chat_id with real patient chat id
CHAT_ID = 382163513

_event_conf = DIALOGS["events"]

EVENTS = [
    Event(
        event_name="morning_med",
        chat_id=CHAT_ID,
        scheduler_args={"hour": 2, "minute": 45},
        main_text=_event_conf["morning_med"]["main_text"],
        retry_text=_event_conf["morning_med"]["retry_text"],
        retries=2,
        retry_delay_seconds=_event_conf["morning_med"]["retry_delay_seconds"],
    ),
    # Event(
    #     event_name="water",
    #     chat_id=CHAT_ID,
    #     scheduler_args={"hour": 11, "minute": 0},
    #     main_text=_event_conf['water']['main_text'],
    #     retry_text=_event_conf['water']['retry_text'],
    #     retries=2,
    #     retry_delay_seconds=_event_conf['water']['retry_delay_seconds'],
    # ),
]
