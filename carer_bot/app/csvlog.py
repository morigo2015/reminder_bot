# app/csvlog.py
from __future__ import annotations

import csv
from datetime import datetime
from typing import Optional

from . import config
from .utils import ensure_dir, format_kyiv

_HEADER = [
    "ts_local",
    "tz",
    "scenario",
    "event",
    "patient_id",
    "group_chat_id",
    "med_id",
    "kind",
    "due_at",
    "action",
    "text",
    "tg_message_id",
]

# Detail logs (per request)
_PILLS_DETAIL_FILE = f"{config.LOG_DIR}/pills_detail.csv"
_PILLS_DETAIL_HEADER = ["date", "time", "patient_id", "label", "nags", "result"]

_PRESSURE_DETAIL_FILE = f"{config.LOG_DIR}/pressure_detail.csv"
_PRESSURE_DETAIL_HEADER = ["type", "date", "time", "patient_id", "sys", "dia", "pulse"]


def _ensure_file():
    ensure_dir(config.LOG_DIR)
    try:
        with open(config.CSV_FILE, "x", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_HEADER)
    except FileExistsError:
        pass


def _ensure_detail_files():
    ensure_dir(config.LOG_DIR)
    try:
        with open(_PILLS_DETAIL_FILE, "x", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_PILLS_DETAIL_HEADER)
    except FileExistsError:
        pass
    try:
        with open(_PRESSURE_DETAIL_FILE, "x", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_PRESSURE_DETAIL_HEADER)
    except FileExistsError:
        pass


def csv_append(
    *,
    scenario: str,
    event: str,
    patient_id: int,
    group_chat_id: int,
    med_id: Optional[int] = None,
    kind: Optional[str] = None,
    due_at: Optional[datetime] = None,
    action: Optional[str] = None,
    text: Optional[str] = None,
    tg_message_id: Optional[int] = None,
) -> None:
    _ensure_file()
    row = [
        format_kyiv(datetime.now(config.TZ)),
        "Europe/Kyiv",
        scenario,
        event,
        patient_id,
        group_chat_id,
        "" if med_id is None else med_id,
        "" if kind is None else kind,
        "" if due_at is None else format_kyiv(due_at),
        "" if action is None else action,
        "" if text is None else text,
        "" if tg_message_id is None else tg_message_id,
    ]
    with open(config.CSV_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


# ---- Thin helpers to reduce repetition ----
def log_med(
    *,
    event: str,
    patient_id: int,
    med_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
    action: Optional[str] = None,
    text: Optional[str] = None,
    tg_message_id: Optional[int] = None,
) -> None:
    group_chat_id = config.PATIENTS[patient_id]["group_chat_id"]
    csv_append(
        scenario="pill",
        event=event,
        patient_id=patient_id,
        group_chat_id=group_chat_id,
        med_id=med_id,
        due_at=due_at,
        action=action,
        text=text,
        tg_message_id=tg_message_id,
    )


def log_measure(
    *,
    event: str,
    patient_id: int,
    kind: str,
    action: Optional[str] = None,
    text: Optional[str] = None,
    tg_message_id: Optional[int] = None,
) -> None:
    group_chat_id = config.PATIENTS[patient_id]["group_chat_id"]
    csv_append(
        scenario="measure",
        event=event,
        patient_id=patient_id,
        group_chat_id=group_chat_id,
        kind=kind,
        action=action,
        text=text,
        tg_message_id=tg_message_id,
    )


# ---- Detail logs (new) ----
def log_pills_detail(*, patient_id: int, label: str, nags: int, result: str) -> None:
    _ensure_detail_files()
    now = datetime.now(config.TZ)
    with open(_PILLS_DETAIL_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M"),
                patient_id,
                label,
                nags,
                result,
            ]
        )


def log_pressure_detail(
    *, patient_id: int, sys: int, dia: int, pulse: int, type_: str = "bp"
) -> None:
    _ensure_detail_files()
    now = datetime.now(config.TZ)
    with open(_PRESSURE_DETAIL_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [
                type_,
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M"),
                patient_id,
                sys,
                dia,
                pulse,
            ]
        )
