from __future__ import annotations
from aiogram import Bot
from app import config
from app.db import pills
from app.util import timez
from app.bot import texts_uk
from app.util.retry import with_retry


def _patient_cfg(patient_id: str) -> dict | None:
    for p in config.PATIENTS:
        if p["id"] == patient_id:
            return p
    return None


async def sweep(bot: Bot):
    rows = await pills.overdue_candidates()
    for patient_id, d, dose, age_min in rows:
        pcfg = _patient_cfg(patient_id)
        if not pcfg:
            continue
        window = pcfg.get("pills", {}).get("confirm_window_min", config.DEFAULT_CONFIRM_WINDOW_MIN)
        if age_min >= window:
            # Send final to patient
            chat_id = pcfg["chat_id"]
            await with_retry(bot.send_message, chat_id, texts_uk.render("pills.final"))
            # Nurse escalation
            label = timez.pill_label(dose, d)
            t_local = pcfg.get("pills", {}).get("times", {}).get(dose)
            time_local_str = timez.planned_time_str(t_local) if t_local else "—"
            msg = texts_uk.render(
                "pills.escalation",
                name=pcfg["name"], label=label, time_local=time_local_str, minutes=age_min,
            )
            await with_retry(bot.send_message, config.NURSE_CHAT_ID, msg)
            # Mark escalated
            await pills.mark_escalated(patient_id, d, dose)
