# app/csvlog.py
from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Any, Optional

from . import config

# ---- Paths ----
LOG_DIR = (
    config.LOG_DIR if hasattr(config, "LOG_DIR") else os.path.join(os.getcwd(), "logs")
)
os.makedirs(LOG_DIR, exist_ok=True)

_EVENTS_CSV = os.path.join(LOG_DIR, "events.csv")
# A wide, forward-compatible header. Keep columns stable; leave empty strings for unused.
_EVENTS_HDR = [
    "date",  # YYYY-MM-DD (local)
    "time",  # HH:MM:SS (local)
    "patient_id",
    "group_chat_id",
    "scenario",  # pill | measure | other
    "event",  # EV_* from app.events
    "kind",  # e.g. "bp" for measure rows, else ""
    "med_id",  # for pill rows, else ""
    "due_at",  # YYYY-MM-DD HH:MM (local) if applicable
    "text",  # trimmed user/system text (<=500 chars)
    "action",  # small flags like auto_swapped, bp_missing_type, etc
    "tg_message_id",  # Telegram message id if applicable
]

# Detail CSVs
_PILLS_DETAIL_CSV = os.path.join(LOG_DIR, "pills_detail.csv")
_PILLS_DETAIL_HDR = [
    "date",
    "time",
    "patient_id",
    "label",
    "nags",
    "result",
    "tg_message_id",
]

_PRESSURE_DETAIL_CSV = os.path.join(LOG_DIR, "pressure_detail.csv")
_PRESSURE_DETAIL_HDR = [
    "date",
    "time",
    "patient_id",
    "type",
    "sys",
    "dia",
    "pulse",
    "tg_message_id",
]


# ---- Helpers ----
def _now_local() -> datetime:
    return datetime.now(config.TZ)


def _ensure_file(path: str, header: list[str]) -> None:
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)


def _append_row(path: str, row: list[Any]) -> None:
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


# ---- Public API (kept compatible with repo callsites) ----
def csv_append(
    *,
    scenario: str,
    event: str,
    patient_id: int,
    group_chat_id: Optional[int] = None,
    kind: str = "",
    med_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
    text: Optional[str] = None,
    action: Optional[str] = None,
    tg_message_id: Optional[int] = None,
) -> None:
    """
    Generic wide events logger. Most callsites should use log_med / log_measure,
    but some (e.g., 'other' acks) call this directly.
    """
    _ensure_file(_EVENTS_CSV, _EVENTS_HDR)
    ts = _now_local()
    # Resolve group id if not provided
    if group_chat_id is None:
        try:
            group_chat_id = int(config.PATIENTS[patient_id]["group_chat_id"])
        except Exception:
            group_chat_id = 0

    row = [
        ts.strftime("%Y-%m-%d"),
        ts.strftime("%H:%M:%S"),
        int(patient_id),
        group_chat_id,
        scenario,
        event,
        kind or "",
        ("" if med_id is None else int(med_id)),
        (
            ""
            if due_at is None
            else due_at.astimezone(config.TZ).strftime("%Y-%m-%d %H:%M")
        ),
        (text or "").replace("\n", " ")[:500],
        (action or ""),
        ("" if tg_message_id is None else int(tg_message_id)),
    ]
    _append_row(_EVENTS_CSV, row)


def log_med(
    *,
    event: str,
    patient_id: int,
    med_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
    text: Optional[str] = None,
    action: Optional[str] = None,
    tg_message_id: Optional[int] = None,
) -> None:
    """
    Pills scenario event.
    """
    csv_append(
        scenario="pill",
        event=event,
        patient_id=patient_id,
        med_id=med_id,
        due_at=due_at,
        text=text,
        action=action,
        tg_message_id=tg_message_id,
    )


def log_measure(
    *,
    event: str,
    patient_id: int,
    kind: str,
    text: Optional[str] = None,
    action: Optional[str] = None,
    tg_message_id: Optional[int] = None,
) -> None:
    """
    Measure scenario event (e.g., BP).
    """
    csv_append(
        scenario="measure",
        event=event,
        patient_id=patient_id,
        kind=kind,
        text=text,
        action=action,
        tg_message_id=tg_message_id,
    )


def log_pills_detail(
    *,
    patient_id: int,
    label: str,
    nags: int,
    result: str,
    tg_message_id: Optional[int] = None,
) -> None:
    """
    Append a row into pills_detail.csv.
    """
    _ensure_file(_PILLS_DETAIL_CSV, _PILLS_DETAIL_HDR)
    ts = _now_local()
    row = [
        ts.strftime("%Y-%m-%d"),
        ts.strftime("%H:%M:%S"),
        int(patient_id),
        label,
        int(nags),
        result,
        ("" if tg_message_id is None else int(tg_message_id)),
    ]
    _append_row(_PILLS_DETAIL_CSV, row)


def log_pressure_detail(
    *,
    patient_id: int,
    sys: int,
    dia: int,
    pulse: int,
    type_: str,
    tg_message_id: Optional[int] = None,
) -> None:
    """
    Append a row into pressure_detail.csv. Note the required 'type_' column
    which stores the canonicalized BP type (e.g., 'швидко').
    """
    _ensure_file(_PRESSURE_DETAIL_CSV, _PRESSURE_DETAIL_HDR)
    ts = _now_local()
    row = [
        ts.strftime("%Y-%m-%d"),
        ts.strftime("%H:%M:%S"),
        int(patient_id),
        type_,
        int(sys),
        int(dia),
        int(pulse),
        ("" if tg_message_id is None else int(tg_message_id)),
    ]
    _append_row(_PRESSURE_DETAIL_CSV, row)
