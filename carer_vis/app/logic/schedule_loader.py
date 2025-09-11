# app/logic/schedule_loader.py
from __future__ import annotations

import asyncio
import logging
import re
from datetime import time
from typing import Dict, Optional, Tuple

from app import config
from app.integrations.gsheets import fetch_schedule_values

logger = logging.getLogger(__name__)

EVENT_MORNING = "ліки - утро"
EVENT_EVENING = "ліки - вечір"
EVENT_BP = "тиск"

_EVENT_MAP = {
    EVENT_MORNING: ("pills", "morning"),
    EVENT_EVENING: ("pills", "evening"),
    EVENT_BP: ("bp", "time"),
}

_TIME_RE = re.compile(r"^\s*(\d{2}):(\d{2})\s*$")


class ScheduleError(Exception):
    pass


def _parse_hhmm_to_time(s: str) -> time:
    m = _TIME_RE.match(s or "")
    if not m:
        raise ScheduleError(f"Invalid time format: '{s}' (expected HH:MM)")
    hh = int(m.group(1))
    mm = int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ScheduleError(f"Invalid time value: '{s}' (0<=HH<=23, 0<=MM<=59)")
    return time(hh, mm, tzinfo=config.TZ)


def _fmt_time(t: Optional[time]) -> str:
    return "—" if t is None else f"{t.hour:02d}:{t.minute:02d}"


def _apply_patient_times(
    patient: dict, pills_times: Dict[str, time], bp_time: Optional[time]
) -> None:
    # Inject pills.times
    pills_cfg = patient.setdefault("pills", {}) or {}
    pills_cfg["times"] = pills_times
    # Inject/clear bp.time
    bp_cfg = patient.setdefault("bp", {}) or {}
    if bp_time is None:
        bp_cfg.pop("time", None)
    else:
        bp_cfg["time"] = bp_time


async def _load_single_patient(patient: dict) -> Tuple[Dict[str, time], Optional[time]]:
    spreadsheet_id = patient.get("gdrive_file_id")
    if not spreadsheet_id:
        raise ScheduleError(f"Patient '{patient.get('id')}' missing gdrive_file_id")

    # Fetch rows from Google Sheets
    values = await fetch_schedule_values(
        spreadsheet_id, config.GSHEETS_SCHEDULE_SHEET_NAME
    )
    if not values:
        # Empty sheet is acceptable => no events configured
        values = [["Подія", "Час"]]

    # Optional: validate headers if present
    header = [c.strip().lower() for c in (values[0] if values else []) + ["", ""]][:2]
    if header and (header[0] not in ("подія", "подiя") or header[1] != "час"):
        logger.debug(
            "schedule: header unexpected for patient=%s: %s", patient.get("id"), header
        )

    pills_times: Dict[str, time] = {}
    bp_time: Optional[time] = None

    # Process data rows (from row 2)
    for idx, row in enumerate(values[1:], start=2):
        if not row or all((c or "").strip() == "" for c in row):
            continue
        raw_event = (row[0] if len(row) >= 1 else "").strip().lower()
        raw_time = (row[1] if len(row) >= 2 else "").strip()

        if raw_event == "":
            logger.debug(
                "schedule: skip empty event row=%d patient=%s", idx, patient.get("id")
            )
            continue

        if raw_event not in _EVENT_MAP:
            logger.debug(
                "schedule: unknown event '%s' row=%d patient=%s",
                raw_event,
                idx,
                patient.get("id"),
            )
            continue  # ignore unknown events silently as agreed

        # Parse time (must be valid)
        t_local = _parse_hhmm_to_time(raw_time)

        domain, key = _EVENT_MAP[raw_event]
        if domain == "pills":
            if key in pills_times:
                raise ScheduleError(
                    f"Duplicate event '{raw_event}' for patient '{patient.get('id')}' (row {idx})"
                )
            pills_times[key] = t_local
        elif domain == "bp":
            if bp_time is not None:
                raise ScheduleError(
                    f"Duplicate event '{raw_event}' for patient '{patient.get('id')}' (row {idx})"
                )
            bp_time = t_local

    return pills_times, bp_time


def _print_patient_summary(
    patient: dict, pills_times: Dict[str, time], bp_time: Optional[time]
) -> None:
    # Console-friendly one-liner per patient for monitoring
    line = (
        f"[SCHEDULE] {patient.get('id')} ({patient.get('name')}): "
        f"pills.morning={_fmt_time(pills_times.get('morning'))}, "
        f"pills.evening={_fmt_time(pills_times.get('evening'))}, "
        f"bp={_fmt_time(bp_time)}"
    )
    # Print and log
    print(line)
    logger.info(line)


async def load_all_schedules(*, startup: bool = True) -> None:
    """
    Read schedules for all patients from Google Sheets and inject into config.PATIENTS.
    - On startup: any error -> raise to stop startup (per spec).
    - On refresh: errors are logged and ignored (keep previous values).
    """
    errors: list[str] = []

    for patient in config.PATIENTS:
        try:
            pills_times, bp_time = await _load_single_patient(patient)
            _apply_patient_times(patient, pills_times, bp_time)
            _print_patient_summary(patient, pills_times, bp_time)
        except Exception as e:
            msg = f"Failed to load schedule for patient '{patient.get('id')}': {e}"
            if startup:
                errors.append(msg)
            logger.error(msg)

    if startup and errors:
        # Stop startup with a clear error
        raise ScheduleError("Schedule loading failed:\n  - " + "\n  - ".join(errors))


async def refresh_all_schedules() -> None:
    """
    Periodic refresh that does not stop the bot on failure.
    """
    try:
        await load_all_schedules(startup=False)
    except Exception as e:
        logger.error("Periodic schedule refresh failed: %s", e)


async def start_periodic_refresh() -> None:
    """
    Starts a background loop to refresh schedules every GSHEETS_REFRESH_SECONDS.
    Intended to be launched as an asyncio task by main.py
    """
    interval = max(60, int(getattr(config, "GSHEETS_REFRESH_SECONDS", 600)))
    while True:
        try:
            await refresh_all_schedules()
        except Exception as e:
            logger.error("schedule refresh loop error: %s", e)
        await asyncio.sleep(interval)
