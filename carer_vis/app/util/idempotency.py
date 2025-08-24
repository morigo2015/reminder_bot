# app/util/idempotency.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Set, Optional
from datetime import date, datetime


@dataclass
class DailyFlags:
    day: date
    # Pills: store last repeat send time (UTC) for each reminder base id
    # key = f"{patient_id}:{dose}:{yyyy-mm-dd}"
    pills_last_repeat_utc: Dict[str, datetime] = field(default_factory=dict)

    # BP and Status: once per day (set of patient ids)
    bp_prompted: Set[str] = field(default_factory=set)
    status_prompted: Set[str] = field(default_factory=set)


_current: DailyFlags | None = None


def _ensure(day: date) -> DailyFlags:
    """Rotate daily in-memory flags at date boundary."""
    global _current
    if _current is None or _current.day != day:
        _current = DailyFlags(day)
    return _current


# ---------- Pills (time-based throttling) ----------


def get_last_repeat_time(reminder_base_id: str, day: date) -> Optional[datetime]:
    """
    Returns UTC datetime of the last repeat we sent for this reminder today, or None.
    """
    return _ensure(day).pills_last_repeat_utc.get(reminder_base_id)


def set_last_repeat_time(reminder_base_id: str, day: date, ts_utc: datetime) -> None:
    """
    Records the UTC time when we sent the last repeat for this reminder today.
    """
    _ensure(day).pills_last_repeat_utc[reminder_base_id] = ts_utc


# ---------- BP (once per day) ----------


def mark_bp_prompted(patient_id: str, day: date) -> None:
    _ensure(day).bp_prompted.add(patient_id)


def was_bp_prompted(patient_id: str, day: date) -> bool:
    return patient_id in _ensure(day).bp_prompted


# ---------- Status (once per day) ----------


def mark_status_prompted(patient_id: str, day: date) -> None:
    _ensure(day).status_prompted.add(patient_id)


def was_status_prompted(patient_id: str, day: date) -> bool:
    return patient_id in _ensure(day).status_prompted
