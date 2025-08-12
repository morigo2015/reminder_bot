"""
Runtime configuration for PillsBot.
All times for scheduling/logging are Europe/Kyiv.
"""

from __future__ import annotations

import os
from typing import Any
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------------------
# Core bot settings
# --------------------------------------------------------------------------------------
BOT_TOKEN: str | None = (
    "550433191:AAFkG6atLs_uo0nwphtuiwbwIJeUhwfzCyI"  # fallback if env BOT_TOKEN is not set
)
TIMEZONE = "Europe/Kyiv"
TZ = ZoneInfo(TIMEZONE)

# Retry/escalation configuration
RETRY_INTERVAL_S = 30  # I
MAX_RETRY_ATTEMPTS = 3  # N
TAKING_GRACE_INTERVAL_S = 600  # pre-confirm grace period in seconds

# --------------------------------------------------------------------------------------
# Patterns (centralized: confirmations + measurements)
# --------------------------------------------------------------------------------------
# Confirmation patterns (search-anywhere). Existing behavior unchanged.
CONFIRM_PATTERNS = [
    r"[OoОо][KkКк]",
    r"\bok\b",
    r"\bок\b",
    r"\bтак\b",
    r"\bвже\b",
    r"\bда\b",
    r"\bокей\b",
    r"\bдобре\b",
    r"\+",
    r"^\s*(✅|✔️|👍)\s*$",
    r"\bdone\b",
]

# Measurement definitions (start-anchored; config-only extensibility)
MEASURES: dict[str, dict[str, Any]] = {
    "pressure": {
        "label": "Тиск",
        "patterns": ["тиск", "давление", "BP", "pressure"],
        "csv_file": "pillsbot/logs/pressure.csv",
        "parser_kind": "int3",  # exactly three integers
        "separators": [" ", ",", "/"],  # allowed separators between the three numbers
    },
    "weight": {
        "label": "Вага",
        "patterns": ["вага", "вес", "взвешивание", "weight"],
        "csv_file": "pillsbot/logs/weight.csv",
        "parser_kind": "float1",  # exactly one number
        "decimal_commas": True,  # accept "102,4"
    },
}

# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------
# CSV outcome file (unchanged name for backward compatibility with tests/tools)
LOG_FILE = "pillsbot/logs/pills.csv"

# Human-readable audit trail (separate from CSV)
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
            {"time": "23:58", "text": "Вітамін Д"},
            {"time": "20:00", "text": "Вітамін Д"},
        ],
        # Optional daily measurement checks (per measure)
        "measurement_checks": [
            {"measure_id": "pressure", "time": "21:00"},
            {"measure_id": "weight", "time": "21:00"},
        ],
    },
]


def get_bot_token() -> str:
    token = BOT_TOKEN or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Bot token is not set. Set BOT_TOKEN in config.py or env var BOT_TOKEN."
        )
    return token
