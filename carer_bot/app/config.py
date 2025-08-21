# app/config.py
from __future__ import annotations

from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

# ---- Core settings (PoC) ----
TZ = ZoneInfo("Europe/Kyiv")
DATETIME_FMT = "%Y-%m-%d %H:%M"  # used in messages and CSV

# For PoC we keep these here (no env). Replace later with env vars.
# NOTE: use a bot token for your environment when running.
BOT_TOKEN = "550433191:AAFkG6atLs_uo0nwphtuiwbwIJeUhwfzCyI"

# Single caregiver escalation channel (for ALL patients)
CAREGIVER_CHAT_ID = 7391874317  # group/supergroup id

# Logging
LOG_DIR = "./logs"  # will be created on first write
CSV_FILE = f"{LOG_DIR}/events.csv"

# Debug
DEBUG_MODE: bool = False
# When DEBUG_MODE=True, nags (pill + clarify) will honor seconds, not minutes (fast loops for tests)
# Tuple form allows us to reuse 0-index consistently (explicitness > magic).
DEBUG_NAG_SECONDS: Tuple[int, int] = (8, 15)  # (pill_nag, clarify_nag)

# ---- Defaults (overridable per patient) ----
DEFAULTS: Dict[str, int] = {
    "pill_nag_after_minutes": 15,
    "pill_escalate_after_minutes": 60,
    "bp_clarify_nag_after_minutes": 20,
    "bp_escalate_after_minutes": 60,
}

# ---- Patients (PoC) ----
# All per-patient specifics live here in the MVP. No DB for PoC.
PATIENTS: Dict[int, Dict] = {
    1: {
        "name": "Ірина",
        "group_chat_id": -1002223334445,  # private group where bot/patient/caregiver are members
        "pill_times_hhmm": ["20:58", "20:00"],
        # Optional per-patient overrides (uncomment to customize)
        # "pill_nag_after_minutes": 10,
        # "pill_escalate_after_minutes": 45,
        # "bp_clarify_nag_after_minutes": 15,
        # "bp_escalate_after_minutes": 45,
        # Labels and daypart threshold (used in messages and CSV)
        "labels": {
            "weekday": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"],
            "daypart": {
                "morning": "ранок",
                "day": "день",
                "evening": "вечір",
                "night": "ніч",
            },
            "threshold_hhmm": "16:00",  # for daypart labeling in prompts/logs
        },
    },
}


# ---- Helper: consistent job IDs (APScheduler) ----
def job_id_for_med(patient_id: int, med_id: int) -> str:
    """Deterministic IDs like 'med:1:0' per scheduled dose ordinal."""
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


# ---- Validation helpers (fail fast) ----
def _is_hhmm(s: str) -> bool:
    if len(s) != 5 or s[2] != ":":
        return False
    hh, mm = s.split(":")
    return hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


def _unique(seq: List[str]) -> bool:
    return len(seq) == len(set(seq))


def fail_fast_config() -> None:
    # caregiver channel present
    assert isinstance(CAREGIVER_CHAT_ID, int), "CAREGIVER_CHAT_ID must be an integer"
    # defaults sane
    for k in (
        "pill_nag_after_minutes",
        "pill_escalate_after_minutes",
        "bp_clarify_nag_after_minutes",
        "bp_escalate_after_minutes",
    ):
        assert k in DEFAULTS and int(DEFAULTS[k]) > 0, (
            f"DEFAULTS['{k}'] must be positive int"
        )
    # patients validate
    assert isinstance(PATIENTS, dict) and PATIENTS, "PATIENTS must be a non-empty dict"
    for pid, cfg in PATIENTS.items():
        assert "group_chat_id" in cfg, f"patient {pid}: missing group_chat_id"
        assert isinstance(cfg["group_chat_id"], int), (
            f"patient {pid}: group_chat_id must be int"
        )
        times = cfg.get("pill_times_hhmm", [])
        for t in times:
            assert _is_hhmm(t), f"patient {pid}: bad HH:MM in pill_times_hhmm: {t}"
        assert _unique(times), f"patient {pid}: duplicate values in pill_times_hhmm"
        labels = cfg.get("labels", {})
        weekday = labels.get("weekday", [])
        assert len(weekday) == 7, f"patient {pid}: labels.weekday must have 7 items"
        thr = labels.get("threshold_hhmm", "16:00")
        assert _is_hhmm(thr), f"patient {pid}: labels.threshold_hhmm must be HH:MM"
    # debug seconds if enabled
    if DEBUG_MODE:
        assert DEBUG_NAG_SECONDS[0] > 0 and DEBUG_NAG_SECONDS[1] > 0, (
            "DEBUG_NAG_SECONDS must be positive"
        )
