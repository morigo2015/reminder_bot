from zoneinfo import ZoneInfo
from datetime import time

# --- Timezone ---
TZ = ZoneInfo("Europe/Kyiv")

# --- Telegram (temporary: keep here per spec) ---
BOT_TOKEN = "550433191:AAFkG6atLs_uo0nwphtuiwbwIJeUhwfzCyI"
NURSE_CHAT_ID = 7391874317  # private chat id

# --- MySQL connection ---
DB = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "igor",
    "password": "1",
    "db": "carer",
}

# --- Defaults (can be overridden per patient) ---
DEFAULT_REPEAT_REMINDER_MIN = 10
DEFAULT_CONFIRM_WINDOW_MIN = 25
DEFAULT_INITIAL_SEND_GRACE_MIN = 5  # global grace, keep it simple
TICK_SECONDS = 60
SWEEP_SECONDS = 300
USE_STATUS = False  # Set to False to disable health status processing

# --- Patients ---
# id must match [a-z0-9_-]+ (used in callback payloads)
PATIENTS = [
    {
        "id": "alice",
        "chat_id": 382163513,
        "name": "Мама",
        "pills": {
            "times": {
                "morning": time(2, 1, tzinfo=TZ),
                # "evening": time(23, 36, tzinfo=TZ),
            },
            "repeat_min": 2,  # per-patient override
            "confirm_window_min": 8,  # per-patient override
        },
        "bp": {
            "time": time(0, 25, tzinfo=TZ),
            "safe_ranges": {"sys": (90, 220), "dia": (50, 140), "pulse": (40, 150)},
        },
    },
]

# --- Daily health status ---
STATUS = {
    # "time": time(18, 0, tzinfo=TZ),
    # initial examples; later refined with medical input
    "alert_regexes": [
        r"(?i)сильн(ий|а) біль",
        # r"(?i)сильн(ий|а) біль у грудях|коротке дихання|задишка",
        # r"(?i)запамороченн(я|ям)|втрата свідомості|непритомн",
        # r"(?i)сильний головний біль|сплутаність свідомості",
        r"(?i)сильний головний біль",
        # r"(?i)аритмія|нерівн(ий|е) серцебиття",
    ],
}
