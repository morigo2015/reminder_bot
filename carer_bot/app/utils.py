# app/utils.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple

from . import config


def now_local() -> datetime:
    return datetime.now(config.TZ)


def format_kyiv(dt: datetime) -> str:
    return dt.astimezone(config.TZ).strftime(config.DATETIME_FMT)


def ensure_dir(p: str) -> None:
    Path(p).mkdir(parents=True, exist_ok=True)


def parse_hhmm(hhmm: str) -> Tuple[int, int]:
    hh, mm = hhmm.split(":")
    return int(hh), int(mm)


def any_substr(s: str, keys: Iterable[str]) -> bool:
    low = s.lower()
    return any(k in low for k in keys)
