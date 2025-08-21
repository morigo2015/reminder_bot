# app/config.py
from __future__ import annotations
from zoneinfo import ZoneInfo

# ---- Core settings (PoC) ----
TZ = ZoneInfo("Europe/Kyiv")
DATETIME_FMT = "%Y-%m-%d %H:%M"  # used in messages and CSV

# For PoC we keep these here (no env). Replace later with env vars.
BOT_TOKEN = "550433191:AAFkG6atLs_uo0nwphtuiwbwIJeUhwfzCyI"

# Single caregiver escalation channel (for ALL patients)
CARE_GIVER_CHAT_ID = 7391874317  # group/supergroup id

# Logging
LOG_DIR = "./logs"  # will be created on first write

# Generic dedupe window for prompts (minutes)
DEDUPE_MIN = 20

# Photo confirmation window relative to scheduled time (minutes)
# Window [-60 ; +120] == [-1h ; +2h]
PHOTO_CONFIRM_WINDOW = (-60, 120)

# Confirmation lexicon (case-insensitive)
CONFIRM_OK = {"прийняла", "прийняв", "так", "да", "є"}

# ---- Feature flags ----
FEATURE_ONBOARD_FEEDBACK = (
    True  # one-time "not onboarded" message for unknown groups/users
)
DEBUG_MODE = True
DEBUG_NAG_SECONDS = [
    10,
    30,
    90,
]  # not used for BP reminder; used for pill nags if DEBUG_MODE

# ---- Defaults for thresholds / timings ----
DEFAULTS = {
    "bp_thresholds": {
        "sys_min": 80,
        "sys_max": 260,
        "dia_min": 60,
        "dia_max": 140,
        "pulse_min": 40,
        "pulse_max": 200,  # alert if outside inclusive bounds
    },
    # Mixed delimiters allowed between numbers: spaces, ',', '/', '-'
    "bp_delimiters_regex": r"[\s,\-\/]+",
    # Pills timing (minutes)
    "pill_nag_after_minutes": 15,
    "pill_escalate_after_minutes": 45,
    # BP timing: one reminder per day (no reminder-nag).
    # Clarification nag is allowed if user's reply was invalid/incomplete.
    "bp_clarify_nag_after_minutes": 15,
    "bp_escalate_after_minutes": 45,  # escalate if no valid value after reminder
}

# ---- Seed data (PoC) ----
# NOTE: Group-based communication:
#   - patient_user_id : Telegram user ID of the patient (who is allowed to talk to bot)
#   - group_chat_id   : Private group chat where bot posts pill/BP messages (visible to relatives)
#
# There is NO per-patient caregiver chat now (single CARE_GIVER_CHAT_ID used for escalations).
PATIENTS = {
    1: {
        "name": "Марія",
        "patient_user_id": 382163513,  # patient's personal Telegram user id
        "group_chat_id": -1002690368389,  # private group for this patient (bot + family)
        # ---- Labels & daypart (used for dose labels like "Пн/р") ----
        # weekday[0..6] = Mon..Sun
        "labels": {
            "weekday": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
            "daypart": {"morning": "р", "evening": "в"},
            "threshold_hhmm": "13:00",
        },
        # ---- Pill schedule (index position = med_id) ----
        "pill_times_hhmm": ["20:11", "20:30"],
        # ---- BP collection ----
        "bp_types": {
            "швидко": r"(швид\w*|моментально)",
            "довго": r"(довго|повільно)",
        },
        # Optional per-patient thresholds (inclusive bounds). Omit to use DEFAULTS.
        "bp_thresholds": {
            "sys_min": 80,
            "sys_max": 260,
            "dia_min": 60,
            "dia_max": 140,
            "pulse_min": 40,
            "pulse_max": 200,
        },
        # Optional per-patient timing overrides (minutes)
        # "pill_nag_after_minutes": 20,
        # "pill_escalate_after_minutes": 60,
        # "bp_clarify_nag_after_minutes": 20,
        # "bp_escalate_after_minutes": 60,
    },
}

# ---- Measurement reminders (time-of-day). Simple PoC list for BP. ----
# One or more daily BP reminder slots per patient. The "one-per-day" rule is enforced at runtime.
MEASURES = [
    {
        "patient_id": 1,
        "kind": "bp",
        "schedule": {"type": "cron", "hour": 20, "minute": 30},
    },
]


# ---- Helper: deterministic job IDs (APScheduler) ----
def job_id_for_med(patient_id: int, med_id: int) -> str:
    """Deterministic IDs like 'med:1:0' let us update/cancel the exact job later."""
    return f"med:{patient_id}:{med_id}"


def job_id_for_measure(patient_id: int, kind: str) -> str:
    """Deterministic IDs like 'measure:1:bp' for measurement jobs."""
    return f"measure:{patient_id}:{kind}"


def job_id_for_clarify(patient_id: int, kind: str, due_ts: int) -> str:
    """One-off clarify nag job id."""
    return f"clarify:{patient_id}:{kind}:{due_ts}"


def job_id_for_escalate(patient_id: int, kind: str, due_ts: int) -> str:
    """One-off escalation check job id."""
    return f"escalate:{patient_id}:{kind}:{due_ts}"
