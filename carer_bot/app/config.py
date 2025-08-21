# app/config.py
from __future__ import annotations

from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

# ---- Core settings (PoC) ----
TZ = ZoneInfo("Europe/Kyiv")
DATETIME_FMT = "%Y-%m-%d %H:%M"

# For PoC we keep these here.
BOT_TOKEN = "550433191:AAFkG6atLs_uo0nwphtuiwbwIJeUhwfzCyI"

# Caregiver escalation is now a DIRECT MESSAGE to this user id
# (the caregiver must have started the bot at least once)
CAREGIVER_USER_ID = 7391874317  # Telegram user id

# Logging
LOG_DIR = "./logs"
CSV_FILE = f"{LOG_DIR}/events.csv"

# Debug
DEBUG_MODE: bool = True
# When DEBUG_MODE=True, nags (pill + clarify) honor seconds (fast loops for tests)
DEBUG_NAG_SECONDS: Tuple[int, int] = (8, 15)  # (pill_nag, clarify_nag)

# ---- Defaults (overridable per patient) ----
DEFAULTS: Dict[str, int] = {
    "pill_nag_after_minutes": 15,
    "pill_escalate_after_minutes": 1,  # 60,
    "bp_clarify_nag_after_minutes": 20,
    "bp_escalate_after_minutes": 60,
}

# ---- Patients (PoC) ----
PATIENTS: Dict[int, Dict] = {
    1: {
        "name": "Надія Микитівна",
        "group_chat_id": -1002690368389,
        "pill_times_hhmm": ["22:39", "20:00"],
        # Optional: restrict who can post as the patient (Telegram user id)
        # "patient_user_id": 123456789,
        "labels": {
            "weekday": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
            "daypart": {
                "morning": "ранок",
                "evening": "вечір",
            },
            "threshold_hhmm": "16:00",
        },
    },
}


# ---- Helper: config access ----
def cfg(pid: int, key: str, default_key: str) -> int:
    """Uniform per-patient minutes lookup with project defaults."""
    return int(PATIENTS[pid].get(key, DEFAULTS[default_key]))


# ---- Job ID helpers (include date key) ----
def job_id_med(pid: int, mid: int, ymd: str) -> str:
    return f"med:{pid}:{mid}:{ymd}"


def job_id_med_nag(pid: int, mid: int, ymd: str) -> str:
    return f"med_nag:{pid}:{mid}:{ymd}"


def job_id_med_escalate(pid: int, mid: int, ymd: str) -> str:
    return f"med_escalate:{pid}:{mid}:{ymd}"


def job_id_bp_clarify(pid: int, ymd: str) -> str:
    return f"bp_clarify:{pid}:{ymd}"


def job_id_bp_escalate(pid: int, ymd: str) -> str:
    return f"bp_escalate:{pid}:{ymd}"


# ---- Validation helpers (fail fast) ----
def _is_hhmm(s: str) -> bool:
    if len(s) != 5 or s[2] != ":":
        return False
    hh, mm = s.split(":")
    return hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


def _unique(seq: List[str]) -> bool:
    return len(seq) == len(set(seq))


def fail_fast_config() -> None:
    errors: List[str] = []
    if not isinstance(CAREGIVER_USER_ID, int):
        errors.append("CAREGIVER_USER_ID must be an integer Telegram user id")
    for k in (
        "pill_nag_after_minutes",
        "pill_escalate_after_minutes",
        "bp_clarify_nag_after_minutes",
        "bp_escalate_after_minutes",
    ):
        if k not in DEFAULTS or int(DEFAULTS[k]) <= 0:
            errors.append(f"DEFAULTS['{k}'] must be positive int")
    if not isinstance(PATIENTS, dict) or not PATIENTS:
        errors.append("PATIENTS must be a non-empty dict")
    else:
        for pid, p in PATIENTS.items():
            if "group_chat_id" not in p or not isinstance(p["group_chat_id"], int):
                errors.append(f"patient {pid}: missing or invalid group_chat_id")
            times = p.get("pill_times_hhmm", [])
            for t in times:
                if not _is_hhmm(t):
                    errors.append(f"patient {pid}: bad HH:MM in pill_times_hhmm: {t}")
            if not _unique(times):
                errors.append(f"patient {pid}: duplicate values in pill_times_hhmm")
            labels = p.get("labels", {})
            weekday = labels.get("weekday", [])
            if len(weekday) != 7:
                errors.append(f"patient {pid}: labels.weekday must have 7 items")
            thr = labels.get("threshold_hhmm", "16:00")
            if not _is_hhmm(thr):
                errors.append(f"patient {pid}: labels.threshold_hhmm must be HH:MM")
    if DEBUG_MODE:
        if (
            len(DEBUG_NAG_SECONDS) != 2
            or DEBUG_NAG_SECONDS[0] <= 0
            or DEBUG_NAG_SECONDS[1] <= 0
        ):
            errors.append("DEBUG_NAG_SECONDS must be a tuple of two positive ints")
    if errors:
        raise AssertionError("Config errors:\n- " + "\n- ".join(errors))
