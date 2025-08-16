"""
Runtime configuration for PillsBot (v4).
All times for scheduling/logging are Europe/Kyiv.
"""

from __future__ import annotations

import os
from typing import Any
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------------------
# Core bot settings
# --------------------------------------------------------------------------------------
# IMPORTANT: no hardcoded token in repo; provide via env or explicit override
BOT_TOKEN: str | None = None
TIMEZONE = "Europe/Kyiv"
TZ = ZoneInfo(TIMEZONE)

# Retry/escalation configuration
RETRY_INTERVAL_S = 60
MAX_RETRY_ATTEMPTS = 3
# TAKING_GRACE_INTERVAL_S = 600  # reserved for future; engine simplified in v4

# --------------------------------------------------------------------------------------
# Patterns (v4: text confirmation list — case-insensitive/trimmed)
# --------------------------------------------------------------------------------------
CONFIRM_PATTERNS = [
    r"^\s*ок\s*$",
    r"^\s*\+\s*$",
    r"^\s*так\s*$",
    r"^\s*окей\s*$",
    r"^\s*прийняв\s*$",
    r"^\s*прийняла\s*$",
]

# --------------------------------------------------------------------------------------
# Measurement definitions (v4)
# --------------------------------------------------------------------------------------
MEASURES: dict[str, dict[str, Any]] = {
    "pressure": {
        "label": "Тиск",
        "patterns": ["тиск", "давление", "bp", "pressure"],
        "csv_file": "pillsbot/logs/pressure.csv",
        "parser_kind": "int2",  # exactly two integers
        "separators": [" ", ",", "/"],  # allowed separators between the two numbers
    },
    "weight": {
        "label": "Вага",
        "patterns": ["вага", "вес", "взвешивание", "weight"],
        "csv_file": "pillsbot/logs/weight.csv",
        "parser_kind": "float1",  # exactly one number
        "decimal_commas": True,  # accept "72,5"
    },
}

# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------
LOG_FILE = "pillsbot/logs/pills.csv"
AUDIT_LOG_FILE = "pillsbot/logs/audit.log"

# --------------------------------------------------------------------------------------
# Patient roster (example/demo values; replace with real IDs)
# --------------------------------------------------------------------------------------
PATIENTS: list[dict[str, Any]] = [
    {
        "patient_id": 382163513,
        "patient_label": "Іван Петров",
        "group_id": -1002690368389,
        "nurse_user_id": 7391874317,
        "doses": [
            {"time": "*", "text": "Вітамін Д"},
            {"time": "22:26", "text": "Парацетамол"},
        ],
        # Optional daily measurement checks (per measure)
        "measurement_checks": [
            {"measure_id": "pressure", "time": "14:16"},
            {"measure_id": "weight", "time": "23:34"},
        ],
    },
]


def get_bot_token() -> str:
    token = BOT_TOKEN or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Bot token is not set. Set env var BOT_TOKEN or override BOT_TOKEN in config.py."
        )
    return token
