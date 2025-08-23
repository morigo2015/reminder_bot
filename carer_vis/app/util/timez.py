from __future__ import annotations
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from typing import Tuple
import calendar

from app import config

WEEKDAYS_UK = [
    "Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя"
]

DOSE_UK = {"morning": "Ранок", "evening": "Вечір"}


def now_utc() -> datetime:
    return datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))


def now_kyiv() -> datetime:
    return now_utc().astimezone(config.TZ)


def date_kyiv(dt: datetime | None = None) -> date:
    return (dt or now_kyiv()).date()


def combine_kyiv(d: date, t: time) -> datetime:
    # time already carries tzinfo=config.TZ per config contract
    return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, tzinfo=config.TZ)


def due_today(local_time: time) -> bool:
    """Has the moment for today's local_time already arrived?"""
    return now_kyiv() >= combine_kyiv(date_kyiv(), local_time)


def weekday_uk(d: date | None = None) -> str:
    d = d or date_kyiv()
    return WEEKDAYS_UK[d.weekday()]


def pill_label(dose: str, d: date | None = None) -> str:
    d = d or date_kyiv()
    return f"{weekday_uk(d)}/{DOSE_UK.get(dose, dose)}"


def planned_time_str(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d} Київ"
