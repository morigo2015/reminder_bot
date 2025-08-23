from __future__ import annotations
from dataclasses import dataclass, field
from typing import Set
from datetime import date

@dataclass
class DailyFlags:
    day: date
    repeats_sent: Set[str] = field(default_factory=set)  # reminder_id tokens sent as repeat
    bp_prompted: Set[str] = field(default_factory=set)   # patient_id set
    status_prompted: Set[str] = field(default_factory=set)

_current: DailyFlags | None = None


def _ensure(day: date) -> DailyFlags:
    global _current
    if _current is None or _current.day != day:
        _current = DailyFlags(day)
    return _current


def mark_repeat(reminder_id: str, day: date) -> None:
    _ensure(day).repeats_sent.add(reminder_id)


def was_repeated(reminder_id: str, day: date) -> bool:
    return reminder_id in _ensure(day).repeats_sent


def mark_bp_prompted(patient_id: str, day: date) -> None:
    _ensure(day).bp_prompted.add(patient_id)


def was_bp_prompted(patient_id: str, day: date) -> bool:
    return patient_id in _ensure(day).bp_prompted


def mark_status_prompted(patient_id: str, day: date) -> None:
    _ensure(day).status_prompted.add(patient_id)


def was_status_prompted(patient_id: str, day: date) -> bool:
    return patient_id in _ensure(day).status_prompted
