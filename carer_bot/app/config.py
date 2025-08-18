# app/config.py
from __future__ import annotations
from zoneinfo import ZoneInfo

# ---- Core settings (PoC) ----
TZ = ZoneInfo("Europe/Kyiv")

# For PoC we keep these here (no env). Replace later with env vars.
# Leave empty if not set; main will fail fast with a clear message.
BOT_TOKEN = "550433191:AAFkG6atLs_uo0nwphtuiwbwIJeUhwfzCyI"

# now: pat is KS, group is for caregiver comm
CARE_GIVER_CHAT_ID = (
    -1002690368389
)  # Telegram group chat ID (negative int for supergroup)

# Logging
LOG_DIR = "./logs"  # Ensure this folder exists (created on first write)

# Dedupe & nags (minutes)
DEDUPE_MIN = 20
NAG_MINUTES = [30, 90, 24 * 60]  # Used when DEBUG_MODE is False

# Photo confirmation window relative to scheduled time (minutes)
# Window [-60 ; +120] == [-1h ; +2h]
PHOTO_CONFIRM_WINDOW = (-60, 120)

# Thresholds
FEVER_C = 38.5
HYPERTENSION_SYS = 180
HYPERTENSION_DIA = 110

# Confirmation lexicon (case-insensitive)
CONFIRM_OK = {"прийняла", "прийняв", "так", "да", "є"}

# ---- Feature flags ----
FEATURE_ONBOARD_FEEDBACK = (
    True  # One-time "not onboarded" message when unknown user writes
)
DEBUG_MODE = True  # Short nag intervals and verbose debug prints
DEBUG_NAG_SECONDS = [10, 30, 90]  # Only used if DEBUG_MODE=True

# ---- Seed data (PoC) ----
PATIENTS = {
    # patient_id: { "name": "Ім'я", "tg_user_id": 123456789 }
    1: {
        "name": "Марія",
        "tg_user_id": 7391874317,
    },  # pat is KS, group is for caregiver comm
    # 2: {"name": "Олег",  "tg_user_id": 222222222},
}

# Medications: one job per item (APScheduler cron-like config).
# Example: daily at 08:00 Kyiv time.
MEDS = [
    {
        "patient_id": 1,
        "med_id": 42,
        "name": "Амлодипін",
        "dose": "5 мг",
        "schedule": {"type": "cron", "hour": 14, "minute": 50},
    },
    # Add more meds here...
]

# Measurements: e.g., BP at 19:00, temperature at 20:00.
MEASURES = [
    {
        "patient_id": 1,
        "kind": "bp",
        "schedule": {"type": "cron", "hour": 19, "minute": 0},
    },
    {
        "patient_id": 1,
        "kind": "temp",
        "schedule": {"type": "cron", "hour": 20, "minute": 0},
    },
    # Add more measurement reminders here...
]


# ---- Helper: consistent job IDs (APScheduler) ----
def job_id_for_med(patient_id: int, med_id: int) -> str:
    """
    Deterministic IDs like 'med:1:42' let us replace/update the exact job later
    (same shape used in Final project with a DB jobstore).
    """
    return f"med:{patient_id}:{med_id}"


def job_id_for_measure(patient_id: int, kind: str) -> str:
    """
    Deterministic IDs like 'measure:1:bp' for measurement jobs.
    """
    return f"measure:{patient_id}:{kind}"
