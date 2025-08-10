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
RETRY_INTERVAL_S = 300  # I
MAX_RETRY_ATTEMPTS = 3  # N
TAKING_GRACE_INTERVAL_S = 600  # pre-confirm grace period in seconds

# --------------------------------------------------------------------------------------
# Confirmation message patterns
# --------------------------------------------------------------------------------------
# Explicit regex patterns that count as a confirmation.
# Compiled with re.IGNORECASE | re.UNICODE by Matcher.
CONFIRM_PATTERNS = [
    # Core "OK" cases (Latin/Cyrillic look-alikes)
    r"[OoОо][KkКк]",
    # Explicit word 'ok' (Latin) and 'ок' (Cyrillic) as standalone words
    r"\bok\b",
    r"\bок\b",
    # Local language short confirms
    r"\bтак\b",  # Ukrainian "yes/okay"
    r"\bвже\b",  # Ukrainian "already/done"
    r"\bда\b",  # Russian "yes"
    r"\bокей\b",  # okay transliteration
    r"\bдобре\b",  # Ukrainian "good/okay"
    # Symbols and emoji
    r"\+",
    r"^\s*(✅|✔️|👍)\s*$",
    r"\bdone\b",
]

# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------
LOG_FILE = "pillsbot/logs/pills.log"

# --------------------------------------------------------------------------------------
# Patient roster (example/demo values; replace with real IDs)
# --------------------------------------------------------------------------------------
PATIENTS: list[dict[str, Any]] = [
    {
        "patient_id": 382163513,  # Telegram user ID of patient
        "patient_label": "Іван Петров",
        "group_id": -1002690368389,  # Telegram group ID for this triad
        "nurse_user_id": 7391874317,  # Nurse personal account user ID
        "doses": [
            {"time": "0:16", "text": "Вітамін Д"},
            {"time": "20:00", "text": "Вітамін Д"},
        ],
    },
]


# --------------------------------------------------------------------------------------
# Utility
# --------------------------------------------------------------------------------------
def get_bot_token() -> str:
    token = BOT_TOKEN or os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Bot token is not set. Set BOT_TOKEN in config.py or env var BOT_TOKEN."
        )
    return token
