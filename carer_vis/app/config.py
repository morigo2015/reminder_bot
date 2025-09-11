# app/config.py
from zoneinfo import ZoneInfo
from datetime import time  # noqa: F401 (kept for compatibility where 'time' type is referenced)

# --- Timezone ---
TZ = ZoneInfo("Europe/Kyiv")

# --- Telegram (temporary: keep here per spec) ---
# BOT_TOKEN = "550433191:AAFkG6atLs_uo0nwphtuiwbwIJeUhwfzCyI"
BOT_TOKEN = "7994158515:AAF_huVgWba-DwJ6b1vNUTl3nxP1Qa4xykE"
NURSE_CHAT_ID = 7391874317  # private chat id

# --- Defaults (can be overridden per patient) ---
DEFAULT_REPEAT_REMINDER_MIN = 10
DEFAULT_CONFIRM_WINDOW_MIN = 25
DEFAULT_INITIAL_SEND_GRACE_MIN = 10  # global grace, keep it simple
TICK_SECONDS = 60
SWEEP_SECONDS = 300
USE_STATUS = False  # Set to False to disable health status processing

# --- Google Sheets/Drive (Service Account) ---
# Service account JSON path (you confirmed service-account flow).
GSHEETS_CREDENTIALS_PATH = "/home/igor/creds/nodal-deck-381522-ebe4f40d6f96.json"

# Sheet name and periodic refresh
GSHEETS_SCHEDULE_SHEET_NAME = "Розклад"
GSHEETS_REFRESH_SECONDS = 600  # refresh schedules every 10 minutes

# --- Patients ---
# NOTE:
#   * Times for pills/bp are NOT configured here anymore.
#   * Each patient has their own Google Sheets workbook with a single sheet "Розклад".
#   * We store the Google Drive FILE ID of that workbook (not the name).
PATIENTS = [
    {
        "id": "mama",  # ASCII stable key (safer for DB FKs & callbacks)
        "chat_id": 382163513,
        "name": "Мама",
        "gdrive_file_id": "1Y3pJoHF0qdC5s_jyYUET8Qcu6Gk0AtfmoedTJCKIWbE",
        "pills": {
            # 'times' will be injected at runtime from the sheet
            "repeat_min": 2,  # per-patient override
            "confirm_window_min": 8,  # per-patient override
        },
        "bp": {
            # 'time' will be injected at runtime from the sheet
            "safe_ranges": {"sys": (90, 220), "dia": (50, 140), "pulse": (40, 150)},
        },
    },
]

# --- Daily health status ---
STATUS = {
    # "time": time(18, 0, tzinfo=TZ),  # may also be injected from a sheet in the future
    "alert_regexes": [
        r"(?i)сильн(ий|а) біль",
        r"(?i)сильний головний біль",
    ],
}

# --- MySQL connection ---
DB = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "igor",
    "password": "1",
    "db": "carer",
}
