from __future__ import annotations
import asyncio
from datetime import date
from aiogram import Bot
from app import config
from app.bot import texts_uk
from app.bot.keyboards import confirm_keyboard
from app.db import pills
from app.util import timez, idempotency
from app.util.retry import with_retry


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
    # Check DB row exists & still unconfirmed long enough
    # We cannot read reminder_ts age cheaply here without extra query; keep minimal: always send one repeat per day if not confirmed after repeat_min elapsed since first send.
    # Simplicity: rely on in-memory once-per-day flag and Sweeper for escalation.
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
            # Repeat window: if due_today and repeat_min passed since initial, send once (best-effort, acceptable duplicates)
            rep_min = patient.get("pills", {}).get("repeat_min", config.DEFAULT_REPEAT_REMINDER_MIN)
            # Use planned local datetime + repeat_min to decide
            due_dt = timez.combine_kyiv(d, t)
            if timez.now_kyiv() >= due_dt.replace(tzinfo=config.TZ) + asyncio.timedelta(minutes=rep_min):
                if await pills.has_reminder_row(patient["id"], d, dose):
                    await maybe_send_repeat(bot, patient, dose, d)

        # BP reminder (daily)
        bp_cfg = patient.get("bp")
        if bp_cfg:
            t = bp_cfg.get("time")
            if t and timez.due_today(t) and not idempotency.was_bp_prompted(patient["id"], d):
                await with_retry(bot.send_message, patient["chat_id"], texts_uk.render("bp.reminder"))
                idempotency.mark_bp_prompted(patient["id"], d)

        # Status prompt (daily)
        st_t = config.STATUS.get("time")
        if st_t and timez.due_today(st_t) and not idempotency.was_status_prompted(patient["id"], d):
            await with_retry(bot.send_message, patient["chat_id"], texts_uk.render("status.prompt"))
            idempotency.mark_status_prompted(patient["id"], d)
