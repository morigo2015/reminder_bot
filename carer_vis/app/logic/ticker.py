# app/logic/ticker.py
"""
Minimal reminder ticker.

Policy:
  1) Initial reminder: send ONLY if we're within a small grace window after the
     scheduled local time (global DEFAULT_INITIAL_SEND_GRACE_MIN in config).
  2) Repeats: only if an initial DB row exists, and only within confirm_window_min.
  3) No backfill, no schedule-derived escalations here. Sweeper escalates ONLY
     for rows that actually exist (i.e., an initial was sent earlier).

Assumptions:
  - time helpers in app.util.timez return tz-aware datetimes for Kyiv and UTC.
  - DB layer (app.db.pills) exposes:
      - upsert_reminder(patient_id, date, dose, label)
      - has_reminder_row(patient_id, date, dose) -> bool
      - get_state(patient_id, date, dose) -> (reminder_ts_utc_naive, confirm_ts_utc_naive) | None
  - idempotency utils in app.util.idempotency for repeat throttling:
      - was_repeated(key, date) / mark_repeat(key, date)
  - texts_uk + confirm_keyboard render the localized copy and inline keyboard.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo
from aiogram import Bot

from app import config
from app.bot import texts_uk
from app.bot.keyboards import confirm_keyboard
from app.db import pills
from app.util import timez, idempotency


def _age_min_since_local(t_local) -> int:
    """
    Minutes from today's scheduled local (Kyiv) time to now (Kyiv).
    Negative => not yet due.
    """
    d = timez.date_kyiv()
    sched = timez.combine_kyiv(d, t_local)  # tz-aware Kyiv datetime
    return int((timez.now_kyiv() - sched).total_seconds() // 60)


def _pill_cfg(patient: dict) -> dict:
    p = patient.get("pills", {}) or {}
    return {
        "repeat_min": p.get("repeat_min", config.DEFAULT_REPEAT_REMINDER_MIN),
        "window_min": p.get("confirm_window_min", config.DEFAULT_CONFIRM_WINDOW_MIN),
        "grace_min": getattr(config, "DEFAULT_INITIAL_SEND_GRACE_MIN", 5),
        "times": p.get("times", {}),
    }


def _callback(patient_id: str, dose: str, d: date) -> str:
    return f"pill:{patient_id}:{dose}:{d.isoformat()}"


async def _send_initial(bot: Bot, patient: dict, dose: str, d: date) -> None:
    """
    Sends the initial reminder and writes the DB row with reminder_ts = UTC NOW.
    """
    label = timez.pill_label(dose, d)
    kb = confirm_keyboard(_callback(patient["id"], dose, d))
    await bot.send_message(
        patient["chat_id"],
        texts_uk.render("pills.initial", label=label),
        reply_markup=kb,
    )
    await pills.upsert_reminder(patient["id"], d, dose, label)


async def _maybe_send_repeat(
    bot: Bot, patient: dict, dose: str, d: date, cfg: dict
) -> None:
    rid_base = f"{patient['id']}:{dose}:{d.isoformat()}"

    state = await pills.get_state(
        patient["id"], d, dose
    )  # (reminder_ts, confirm_ts) or None
    if not state:
        return
    reminder_ts, confirm_ts = state
    if reminder_ts is None or confirm_ts is not None:
        return

    age_min = int(
        (timez.now_utc() - reminder_ts.replace(tzinfo=ZoneInfo("UTC"))).total_seconds()
        // 60
    )

    # Never repeat outside the confirmation window.
    if age_min > cfg["window_min"]:
        return

    # Compute which repeat bucket we're in: 2,4,6,... for repeat_min=2
    bucket = age_min // max(1, cfg["repeat_min"])
    if bucket <= 0:
        return

    rid_bucket = f"{rid_base}:r{bucket}"
    if idempotency.was_repeated(rid_bucket, d):
        return

    label = timez.pill_label(dose, d)
    kb = confirm_keyboard(_callback(patient["id"], dose, d))
    await bot.send_message(
        patient["chat_id"],
        texts_uk.render("pills.repeat", label=label),
        reply_markup=kb,
    )
    idempotency.mark_repeat(rid_bucket, d)


async def tick(bot: Bot) -> None:
    """
    Runs once per TICK_SECONDS (see main.py loop).
    For each patient/dose:
      - If due today and within grace, send initial (if not already sent).
      - If a row exists, consider sending a repeat (capped by window).
    """
    d = timez.date_kyiv()
    now_k = timez.now_kyiv()

    # Optional debug trace; comment out if noisy.
    print({"level": "debug", "where": "tick", "now_kyiv": str(now_k)})

    for patient in config.PATIENTS:
        cfg = _pill_cfg(patient)

        for dose, t_local in cfg["times"].items():
            # Due today?
            if not timez.due_today(t_local):
                # Optional trace
                print(
                    {
                        "level": "debug",
                        "action": "due_check",
                        "patient": patient["id"],
                        "dose": dose,
                        "due": False,
                        "scheduled": f"{t_local.hour:02d}:{t_local.minute:02d}",
                    }
                )
                continue

            age = _age_min_since_local(t_local)
            exists = await pills.has_reminder_row(patient["id"], d, dose)

            print(
                {
                    "level": "debug",
                    "action": "due_check",
                    "patient": patient["id"],
                    "dose": dose,
                    "due": True,
                    "scheduled": f"{t_local.hour:02d}:{t_local.minute:02d}",
                    "age_min": age,
                    "exists": exists,
                }
            )

            # Initial: send only within grace; otherwise skip entirely (no DB writes).
            if not exists and 0 <= age <= cfg["grace_min"]:
                await _send_initial(bot, patient, dose, d)

            # Repeats: only if a row exists; _maybe_send_repeat caps by window.
            if exists:
                await _maybe_send_repeat(bot, patient, dose, d, cfg)
