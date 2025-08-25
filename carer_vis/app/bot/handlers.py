from __future__ import annotations
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from datetime import date

from app import config
from app.logic import parser
from app.db import pills, bp as bp_db, status as status_db
from app.util import timez
from app.bot import texts_uk
from app.util.retry import with_retry

router = Router()

# Helpers

CHAT_TO_PATIENT = {p["chat_id"]: p for p in config.PATIENTS}
ID_TO_PATIENT = {p["id"]: p for p in config.PATIENTS}


def is_patient(msg_or_cb) -> bool:
    chat_id = (
        msg_or_cb.message.chat.id
        if isinstance(msg_or_cb, CallbackQuery)
        else msg_or_cb.chat.id
    )
    return chat_id in CHAT_TO_PATIENT


@router.message(CommandStart())
async def start(message: Message):
    if message.chat.id in CHAT_TO_PATIENT:
        await message.answer("Вітаю! Я буду нагадувати про ліки та збирати показники.")
    elif message.chat.id == config.NURSE_CHAT_ID:
        await message.answer("Канал ескалацій підключено.")


@router.callback_query(F.data.startswith("pill:"))
async def on_pill_confirm(cb: CallbackQuery, bot: Bot):
    # payload: pill:{patient_id}:{dose}:{YYYY-MM-DD}
    try:
        _, pid, dose, dates = cb.data.split(":", 3)
        d = date.fromisoformat(dates)
    except Exception:
        await cb.answer("Невірні дані.", show_alert=True)
        return
    # authorize: only the patient themself can confirm
    p = CHAT_TO_PATIENT.get(cb.message.chat.id)
    if not p or p["id"] != pid:
        await cb.answer("Недоступно.", show_alert=True)
        return

    changed, label, was_escalated = await pills.set_confirm_if_empty(
        pid, d, dose, via="button"
    )
    # Edit original message regardless; append check and remove keyboard
    try:
        text = cb.message.text
        ack_text = texts_uk.render("pills.confirm_ack", label=label)
        if text and ack_text not in text:
            text = text + "\n\n" + ack_text
            await with_retry(
                bot.edit_message_text,
                text,
                chat_id=cb.message.chat.id,
                message_id=cb.message.message_id,
            )
        await with_retry(
            bot.edit_message_reply_markup,
            chat_id=cb.message.chat.id,
            message_id=cb.message.message_id,
            reply_markup=None,
        )
    except Exception:
        pass

    if changed and was_escalated:
        t_local = p.get("pills", {}).get("times", {}).get(dose)
        time_local_str = timez.planned_time_str(t_local) if t_local else "—"
        msg = texts_uk.render(
            "pills.late_confirm", name=p["name"], label=label, time_local=time_local_str
        )
        await with_retry(bot.send_message, config.NURSE_CHAT_ID, msg, parse_mode="HTML")


@router.message()
async def on_message(message: Message, bot: Bot):
    # Ignore nurse chat messages
    if message.chat.id == config.NURSE_CHAT_ID:
        return

    patient = CHAT_TO_PATIENT.get(message.chat.id)
    if not patient or not message.text:
        return

    txt = message.text.strip()

    # 1) BP reading?
    bp = parser.parse_bp(txt)
    if bp:
        side, sys_v, dia_v, pulse_v, hard_fail = bp
        if hard_fail:
            await message.answer(texts_uk.render("bp.error.range"))
            return
        # compare safe ranges
        safe = patient.get("bp", {}).get("safe_ranges", {})
        s_sys = safe.get("sys", (90, 150))
        s_dia = safe.get("dia", (60, 95))
        s_pul = safe.get("pulse", (45, 110))
        out_of_range = not (
            s_sys[0] <= sys_v <= s_sys[1]
            and s_dia[0] <= dia_v <= s_dia[1]
            and s_pul[0] <= pulse_v <= s_pul[1]
        )
        await bp_db.insert_reading(
            patient["id"], side, sys_v, dia_v, pulse_v, out_of_range
        )
        if out_of_range:
            msg = texts_uk.render(
                "bp.out_of_range_nurse",
                name=patient["name"],
                side=side,
                sys=sys_v,
                dia=dia_v,
                pulse=pulse_v,
            )
            await with_retry(bot.send_message, config.NURSE_CHAT_ID, msg)
        return

    # 2) Otherwise, treat as daily health status text
    # Match alert regexes
    match_str = None
    for rx in config.STATUS.get("alert_regexes", []):
        m = __import__("re").search(rx, txt)
        if m:
            match_str = m.group(0)
            break
    await status_db.insert_status(patient["id"], txt, match_str)
    if match_str:
        msg = texts_uk.render(
            "status.alert_nurse", name=patient["name"], match=match_str
        )
        await with_retry(bot.send_message, config.NURSE_CHAT_ID, msg)
