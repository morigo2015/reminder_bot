from __future__ import annotations
from datetime import date, timedelta
from aiogram import Bot
from app import config
from app.bot import texts_uk
from app.bot.keyboards import confirm_keyboard
from app.db import pills
from app.util import timez, idempotency
from app.util.retry import with_retry
from zoneinfo import ZoneInfo


def reminder_id(patient_id: str, dose: str, d: date) -> str:
    return f"{patient_id}:{dose}:{d.isoformat()}"


def callback_payload(patient_id: str, dose: str, d: date) -> str:
    return f"pill:{patient_id}:{dose}:{d.isoformat()}"


async def send_initial(bot: Bot, patient: dict, dose: str, d: date):
    label = timez.pill_label(dose, d)
    text = texts_uk.render("pills.initial", label=label)
    kb = confirm_keyboard(callback_payload(patient["id"], dose, d))
    await with_retry(bot.send_message, patient["chat_id"], text, reply_markup=kb)
    await pills.upsert_reminder(patient["id"], d, dose, label)


async def maybe_send_repeat(bot: Bot, patient: dict, dose: str, d: date):
    rid = reminder_id(patient["id"], dose, d)
    if idempotency.was_repeated(rid, d):
        return
    # Only repeat if still UNCONFIRMED and enough minutes passed since the initial reminder.
    state = await pills.get_state(
        patient["id"], d, dose
    )  # (reminder_ts, confirm_ts) or None
    if not state:
        return
    reminder_ts, confirm_ts = state
    if reminder_ts is None or confirm_ts is not None:
        return
    rep_min = patient.get("pills", {}).get(
        "repeat_min", config.DEFAULT_REPEAT_REMINDER_MIN
    )
    # reminder_ts is stored in UTC (naive). Compare using aware UTC 'now'.
    if timez.now_utc() >= reminder_ts.replace(tzinfo=ZoneInfo("UTC")) + timedelta(
        minutes=rep_min
    ):
        text = texts_uk.render("pills.repeat", label=timez.pill_label(dose, d))
        kb = confirm_keyboard(callback_payload(patient["id"], dose, d))
        await with_retry(bot.send_message, patient["chat_id"], text, reply_markup=kb)
        idempotency.mark_repeat(rid, d)


async def tick(bot: Bot):
    d = timez.date_kyiv()
    for patient in config.PATIENTS:
        # Pills initial
        for dose, t in patient.get("pills", {}).get("times", {}).items():
            if timez.due_today(t):
                # Only send initial once per day per dose (DB-guarded)
                if not await pills.has_reminder_row(patient["id"], d, dose):
                    await send_initial(bot, patient, dose, d)
                # Repeat window: if an initial reminder exists and the confirm hasn't arrived in time, send one repeat.
                if await pills.has_reminder_row(patient["id"], d, dose):
                    await maybe_send_repeat(bot, patient, dose, d)

        # BP reminder (daily)
        bp_cfg = patient.get("bp")
        if bp_cfg:
            t = bp_cfg.get("time")
            if (
                t
                and timez.due_today(t)
                and not idempotency.was_bp_prompted(patient["id"], d)
            ):
                await with_retry(
                    bot.send_message, patient["chat_id"], texts_uk.render("bp.reminder")
                )
                idempotency.mark_bp_prompted(patient["id"], d)

        # Status prompt (daily)
        st_t = config.STATUS.get("time")
        if (
            st_t
            and timez.due_today(st_t)
            and not idempotency.was_status_prompted(patient["id"], d)
        ):
            await with_retry(
                bot.send_message, patient["chat_id"], texts_uk.render("status.prompt")
            )
            idempotency.mark_status_prompted(patient["id"], d)
