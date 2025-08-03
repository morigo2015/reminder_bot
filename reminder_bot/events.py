"""Static list of Event definitions. Replace chat_id values with real ones."""

from .models import Event

EVENTS = [
    Event(
        event_name="morning_med",
        chat_id=382163513,
        scheduler_args={"hour": 1, "minute": 42},
        main_message="Good morning! Take your morning medicine. Reply 'morning_med' once done.",
        retry_message="Reminder: please take your morning medicine and reply 'morning_med'.",
        retries=2,
        retry_delay_seconds=30,
        escalate=True,
    ),
    Event(
        event_name="evening_med",
        chat_id=382163513,
        scheduler_args={"hour": 21, "minute": 0},
        main_message="Good evening! Take your evening medicine. Reply 'evening_med' once done.",
        retry_message="Reminder: please take your evening medicine and reply 'evening_med'.",
        retries=2,
        retry_delay_seconds=300,
        escalate=True,
    ),
]
