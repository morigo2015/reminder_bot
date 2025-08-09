"""
Runtime configuration for PillsBot.
All times for scheduling/logging are Europe/Kyiv.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Dict, Any
from zoneinfo import ZoneInfo

# Read from env by default for safety. You may hardcode for local dev.
BOT_TOKEN: str | None = None  # fallback to env BOT_TOKEN if None
TIMEZONE = "Europe/Kyiv"
TZ = ZoneInfo(TIMEZONE)

# Retry/escalation config
RETRY_INTERVAL_S = 300           # I
MAX_RETRY_ATTEMPTS = 3           # N
TAKING_GRACE_INTERVAL_S = 600    # pre-confirm grace

# Regex patterns (case-insensitive search)
CONFIRM_PATTERNS = [r"OK", r"\bтак\b", r"\bвже\b", r"\bда\b", r"\+"]

LOG_FILE = "pillsbot/logs/pills.log"


# Patient roster (example/demo values; replace with real IDs)
PATIENTS: list[dict[str, Any]] = [
    {
        "patient_id": 111111111,           # Telegram user ID of patient
        "patient_label": "Іван Петров",
        "group_id": -1001234567890,        # Telegram group ID for this triad
        "nurse_user_id": 222222222,        # Nurse personal account user ID
        "doses": [
            {"time": "08:30", "text": "Вітамін Д"},
            {"time": "20:00", "text": "Вітамін Д"},
        ],
    },
]


def get_bot_token() -> str:
    token = BOT_TOKEN or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Bot token is not set. Set BOT_TOKEN in config.py or env var BOT_TOKEN.")
    return token


def validate() -> None:
    from datetime import datetime
    # Basic validation of patient config
    def parse_time_str(t: str) -> None:
        try:
            datetime.strptime(t, "%H:%M")
        except ValueError as e:
            raise ValueError(f"Invalid time '{t}', expected HH:MM") from e

    required_fields = {"patient_id", "patient_label", "group_id", "nurse_user_id", "doses"}
    for p in PATIENTS:
        missing = required_fields - set(p.keys())
        if missing:
            raise ValueError(f"Patient missing fields: {missing}")
        seen_times = set()
        for d in p["doses"]:
            t = d.get("time")
            if t in seen_times:
                raise ValueError(f"Duplicate dose time for patient {p['patient_label']}: {t}")
            seen_times.add(t)
            parse_time_str(t)
            if not d.get("text"):
                raise ValueError(f"Dose text is required for patient {p['patient_label']} at {t}")
