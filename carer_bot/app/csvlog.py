# app/csvlog.py
from __future__ import annotations
import os
import csv
import json
from typing import Optional, Any, Dict
from datetime import datetime
from . import config

HEADER = [
    "date_time_kyiv",
    "patient_id",
    "scenario",
    "event",
    "med_id",
    "measure_kind",
    "due_time_kyiv",
    "pill_label",
    "sys",
    "dia",
    "pulse",
    "bp_type",
    "temp_c",
    "text",
    "photo_file_id",
    "action",
    "nag_count",
    "escalated",
    "tg_message_id",
    "extra_json",
]


def _ensure_dir():
    os.makedirs(config.LOG_DIR, exist_ok=True)


def _now_local() -> datetime:
    from datetime import datetime

    return datetime.now(config.TZ)


def _fmt(dt: Optional[datetime]) -> str:
    return dt.astimezone(config.TZ).strftime(config.DATETIME_FMT) if dt else ""


def csv_append(
    *,
    patient_id: int,
    scenario: str,
    event: str,
    med_id: Optional[int] = None,
    measure_kind: Optional[str] = None,
    due_time_kyiv: Optional[datetime] = None,
    pill_label: Optional[str] = None,
    sys: Optional[int] = None,
    dia: Optional[int] = None,
    pulse: Optional[int] = None,
    bp_type: Optional[str] = None,
    temp_c: Optional[float] = None,
    text: Optional[str] = None,
    photo_file_id: Optional[str] = None,
    action: Optional[str] = None,
    nag_count: Optional[int] = None,
    escalated: bool = False,
    tg_message_id: Optional[int] = None,
    extra_json: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append a single row with the stable header defined in Specs v2.1.
    """
    _ensure_dir()
    fname = os.path.join(
        config.LOG_DIR, f"events_{_now_local().date().isoformat()}.csv"
    )
    new_file = not os.path.exists(fname)
    try:
        with open(fname, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            if new_file:
                w.writerow(HEADER)
            w.writerow(
                [
                    _fmt(_now_local()),
                    patient_id,
                    scenario,
                    event,
                    med_id if med_id is not None else "",
                    measure_kind or "",
                    _fmt(due_time_kyiv),
                    pill_label or "",
                    sys if sys is not None else "",
                    dia if dia is not None else "",
                    pulse if pulse is not None else "",
                    bp_type or "",
                    f"{temp_c:.1f}" if temp_c is not None else "",
                    (text or "").replace("\n", " ").strip(),
                    photo_file_id or "",
                    action or "",
                    nag_count if nag_count is not None else "",
                    "1" if escalated else "0",
                    tg_message_id or "",
                    json.dumps(extra_json or {}, ensure_ascii=False),
                ]
            )
    except Exception as e:
        # Logging must never kill the bot in PoC
        from .utils import dbg

        dbg(f"CSV append failed: {e}")


def emit_config_digest_system() -> None:
    csv_append(
        patient_id=0,
        scenario="system",
        event="config_digest",
        text="Carer v2.1 start",
        extra_json={"tz": "Europe/Kyiv", "datetime_fmt": config.DATETIME_FMT},
    )


def emit_config_digest_patient(patient_id: int, p: dict) -> None:
    weekday = p["labels"]["weekday"]
    threshold = p["labels"]["threshold_hhmm"]
    pill_times = p.get("pill_times_hhmm", [])
    bp_types = list(p.get("bp_types", {}).keys())
    thr = p.get("bp_thresholds", config.DEFAULTS["bp_thresholds"])
    text = (
        f"patient={p.get('name', '')}; pills={pill_times}; threshold={threshold}; "
        f"weekday={weekday}; bp_types={bp_types}; "
        f"bp_thr={{sys:[{thr['sys_min']},{thr['sys_max']}], "
        f"dia:[{thr['dia_min']},{thr['dia_max']}], pulse:[{thr['pulse_min']},{thr['pulse_max']} ]}}"
    )
    csv_append(
        patient_id=patient_id, scenario="system", event="config_digest", text=text
    )
