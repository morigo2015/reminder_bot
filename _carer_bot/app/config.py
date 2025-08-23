# app/config.py
from __future__ import annotations

import re
from typing import Dict, List, Tuple, Optional
from zoneinfo import ZoneInfo

# ---- Core settings (PoC) ----
TZ = ZoneInfo("Europe/Kyiv")
DATETIME_FMT = "%Y-%m-%d %H:%M"

# For PoC we keep these here.
BOT_TOKEN = "550433191:AAFkG6atLs_uo0nwphtuiwbwIJeUhwfzCyI"

# Caregiver escalation is a DIRECT MESSAGE to this user id
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
# NOTE: patient_user_id is REQUIRED (strict moderation by default).
PATIENTS: Dict[int, Dict] = {
    1: {
        "name": "Надія Микитівна",
        "group_chat_id": -1002690368389,
        "patient_user_id": 382163513,
        "pill_times_hhmm": ["00:23", "20:00"],
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

# ---- Blood pressure "types" (canonical -> variants) ----
# These are global for all patients. Variants must be letters-only (unicode).
BP_TYPES: Dict[str, List[str]] = {
    "швидко": ["швидко", "різко", "одразу", "швидкий", "quick"],
    "повільно": ["повільно", "поступово", "slow"],
}

# Precompute variant -> canonical map (lowercased)
_BP_VARIANT_TO_CANON: Dict[str, str] = {}
for canon, variants in BP_TYPES.items():
    for v in variants:
        _BP_VARIANT_TO_CANON[v.lower()] = canon

# Letters-only token (no digits/underscore); unicode-aware.
_LETTERS_ONLY = re.compile(r"^[^\W\d_]+$", re.UNICODE)


def canonicalize_bp_type(token: str) -> Optional[str]:
    """Return canonical bp type for an acceptable leading token; otherwise None."""
    t = (token or "").strip().lower()
    if not t or not _LETTERS_ONLY.match(t):
        return None
    return _BP_VARIANT_TO_CANON.get(t)


# ---- OK confirmation patterns (broadened for backward compatibility) ----
# NOTE:
#  - Short, exact acks remain anchored.
#  - Verb stems are *searched* anywhere in the text with word boundaries.
#  - Negation is handled separately in regex_bank.is_negation(), which runs first.
_OK_CONFIRM_PATTERNS_RAW: List[str] = [
    # Short exact acks
    r"^\s*(так|ок|окей|підтверджую)\s*[.!]?\s*$",
    r"^\s*(ok|okay|done|yes|y)\s*[.!]?\s*$",
    r"^\s*✅\s*$",
    r"^\s*👍\s*$",
    # Ukrainian verb stems
    r"\bприйняв(?!\w)\b",
    r"\bприйняла(?!\w)\b",
    r"\bприйнято(?!\w)\b",
    r"\bвипив(?!\w)\b",
    r"\bвипила(?!\w)\b",
    r"\bготово\b",
    r"\bзробив(?!\w)\b",
    r"\bзробила(?!\w)\b",
    # Russian verb stems
    r"\bпринял(?!\w)\b",
    r"\bприняла(?!\w)\b",
    r"\bвыпил(?!\w)\b",
    r"\bвыпила(?!\w)\b",
    r"\bсделал(?!\w)\b",
    r"\bсделала(?!\w)\b",
    r"\bготово\b",
    # English
    r"\btook\b",
    r"\btaken\b",
    r"\bdone\b",
    r"\bi\s+(took|have\s+taken|did)\b",
]
OK_CONFIRM_PATTERNS = [
    re.compile(p, re.IGNORECASE | re.UNICODE) for p in _OK_CONFIRM_PATTERNS_RAW
]


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
            if "patient_user_id" not in p or not isinstance(p["patient_user_id"], int):
                errors.append(
                    f"patient {pid}: patient_user_id is required and must be int"
                )
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

    # BP types sanity
    if not BP_TYPES:
        errors.append("BP_TYPES must not be empty")
    else:
        # ensure variants are letters-only and non-empty
        for canon, vars_ in BP_TYPES.items():
            if not canon or not vars_:
                errors.append(f"BP_TYPES['{canon}'] must have at least one variant")
            for v in vars_:
                if not _LETTERS_ONLY.match(v):
                    errors.append(
                        f"BP_TYPES['{canon}'] variant '{v}' must be letters-only"
                    )

    # OK patterns sanity
    if not OK_CONFIRM_PATTERNS:
        errors.append("OK_CONFIRM_PATTERNS must not be empty")

    if errors:
        raise AssertionError("Config errors:\n- " + "\n- ".join(errors))
