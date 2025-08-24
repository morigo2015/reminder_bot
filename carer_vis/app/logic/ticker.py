# app/logic/ticker.py
"""
Minimal reminder ticker (pills: time-throttled repeats; BP/Status: once/day).

Policy:
  1) Initial pill reminder: send ONLY if we're within a small grace window after
     the scheduled local time (DEFAULT_INITIAL_SEND_GRACE_MIN).
  2) Pill repeats: only if an initial DB row exists; send when at least
     repeat_min minutes have passed since the *last* repeat we sent,
     and only while still inside the confirmation window.
  3) BP and Status: send at most once per day (also within grace).
  4) No backfill; Sweeper escalates ONLY for rows that exist.

Assumptions:
  - time helpers (app.util.timez) return tz-aware Kyiv/UTC datetimes.
  - DB layer (app.db.pills):
      - upsert_reminder(patient_id, date, dose, label)
      - has_reminder_row(patient_id, date, dose) -> bool
      - get_state(patient_id, date, dose) -> (reminder_ts_utc_naive, confirm_ts_utc_naive) | None
  - idempotency helpers (app.util.idempotency):
      - get_last_repeat_time(reminder_base_id, day) / set_last_repeat_time(...)
      - was_bp_prompted / mark_bp_prompted
      - was_status_prompted / mark_status_prompted
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot

from app import config
from app.bot import texts_uk
from app.bot.keyboards import confirm_keyboard
from app.db import pills
from app.util import timez, idempotency


def _age_min_since_local(t_local) -> int:
    """Minutes from today's scheduled local (Kyiv) time to now (Kyiv)."""
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
    """Send the initial pill reminder and write DB row with reminder_ts=UTC NOW."""
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
    """
    Time-based throttling:
      - Send a repeat if (now_utc - last_repeat_utc) >= repeat_min minutes,
        while still inside the confirmation window and not yet confirmed.
      - First repeat will send as soon as repeat_min minutes pass after initial.
    """
    rid_base = f"{patient['id']}:{dose}:{d.isoformat()}"

    state = await pills.get_state(
        patient["id"], d, dose
    )  # (reminder_ts, confirm_ts) or None
    if not state:
        return
    reminder_ts, confirm_ts = state
    if reminder_ts is None or confirm_ts is not None:
        return

    # Compute age since initial and ensure we are still within the window.
    now_utc = timez.now_utc()
    age_min = int(
        (now_utc - reminder_ts.replace(tzinfo=ZoneInfo("UTC"))).total_seconds() // 60
    )
    if age_min > cfg["window_min"]:
        return

    # Throttle by last repeat time (UTC).
    last_repeat_utc = idempotency.get_last_repeat_time(rid_base, d)
    if last_repeat_utc is not None:
        if (now_utc - last_repeat_utc) < timedelta(minutes=max(1, cfg["repeat_min"])):
            return
    else:
        # No repeat yet; ensure at least repeat_min minutes have passed since initial.
        if age_min < max(1, cfg["repeat_min"]):
            return

    # Send repeat
    label = timez.pill_label(dose, d)
    kb = confirm_keyboard(_callback(patient["id"], dose, d))
    await bot.send_message(
        patient["chat_id"],
        texts_uk.render("pills.repeat", label=label),
        reply_markup=kb,
    )
    idempotency.set_last_repeat_time(rid_base, d, now_utc)


async def tick(bot: Bot) -> None:
    """
    Runs once per TICK_SECONDS (see main.py loop).
    Pills: initial within grace; repeats throttled by time until confirm/escalation.
    BP/Status: once per day max.
    """
    d = timez.date_kyiv()
    now_k = timez.now_kyiv()
    logging.debug(f"tick: now_kyiv={now_k}")

    for patient in config.PATIENTS:
        cfg = _pill_cfg(patient)

        # -------- Pills --------
        for dose, t_local in cfg["times"].items():
            # Due today?
            if not timez.due_today(t_local):
                logging.debug(
                    f"due_check: patient={patient['id']} dose={dose} due=False scheduled={t_local.hour:02d}:{t_local.minute:02d}"
                )
                continue

            age = _age_min_since_local(t_local)
            exists = await pills.has_reminder_row(patient["id"], d, dose)

            logging.debug(
                f"due_check: patient={patient['id']} dose={dose} due=True scheduled={t_local.hour:02d}:{t_local.minute:02d} age_min={age} exists={exists}"
            )

            # Initial: only within grace; otherwise skip (no DB writes).
            if not exists and 0 <= age <= cfg["grace_min"]:
                await _send_initial(bot, patient, dose, d)

            # Repeats: only if a row exists; time-throttled and capped by window.
            if exists:
                await _maybe_send_repeat(bot, patient, dose, d, cfg)

        # -------- BP (once per day) --------
        bp_cfg = patient.get("bp") or {}
        t_bp = bp_cfg.get("time")
        if (
            t_bp
            and timez.due_today(t_bp)
            and not idempotency.was_bp_prompted(patient["id"], d)
        ):
            age_bp = _age_min_since_local(t_bp)
            if 0 <= age_bp <= cfg["grace_min"]:
                await bot.send_message(
                    patient["chat_id"], texts_uk.render("bp.reminder")
                )
                idempotency.mark_bp_prompted(patient["id"], d)

        # -------- Status (once per day) --------
        st_t = (config.STATUS or {}).get("time")
        if (
            st_t
            and timez.due_today(st_t)
            and not idempotency.was_status_prompted(patient["id"], d)
        ):
            age_st = _age_min_since_local(st_t)
            if 0 <= age_st <= cfg["grace_min"]:
                await bot.send_message(
                    patient["chat_id"], texts_uk.render("status.prompt")
                )
                idempotency.mark_status_prompted(patient["id"], d)
