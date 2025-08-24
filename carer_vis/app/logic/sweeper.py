# app/logic/sweeper.py
from __future__ import annotations
from typing import Optional
from aiogram import Bot

from app import config
from app.bot import texts_uk
from app.db import pills
from app.util import timez
from app.util.retry import with_retry


def _find_patient(pid: str) -> Optional[dict]:
    for p in config.PATIENTS:
        if p.get("id") == pid:
            return p
    return None


def _confirm_window_min(patient: dict) -> int:
    p = patient.get("pills") or {}
    return p.get(
        "confirm_window_min", getattr(config, "DEFAULT_CONFIRM_WINDOW_MIN", 25)
    )


async def sweep(bot: Bot) -> None:
    """
    Escalate ONLY rows that exist (initial was sent) and are past the confirm window.
    Sends a final notice to the patient + an escalation to the nurse, then marks escalated.
    """
    rows = await pills.overdue_candidates()  # (patient_id, date_kyiv, dose, age_min)
    for pid, d, dose, age_min in rows:
        patient = _find_patient(pid)
        if not patient:
            print(
                {"level": "warn", "action": "sweeper.skip.unknown_patient", "pid": pid}
            )
            continue

        window_min = _confirm_window_min(patient)
        if age_min < window_min:
            continue

        # Mark escalated first (idempotent)
        updated = await pills.mark_escalated(pid, d, dose)
        if not updated:
            continue

        # Final notice to patient
        await with_retry(
            bot.send_message, patient["chat_id"], texts_uk.render("pills.final")
        )

        # Nurse escalation
        label = timez.pill_label(dose, d)
        t_local = (patient.get("pills") or {}).get("times", {}).get(dose)
        time_local_str = timez.planned_time_str(t_local) if t_local else "—"
        msg = texts_uk.render(
            "pills.escalation",
            name=patient["name"],
            label=label,
            time_local=time_local_str,
            minutes=age_min,
        )
        await with_retry(bot.send_message, config.NURSE_CHAT_ID, msg, parse_mode="HTML")

        print(
            {
                "level": "info",
                "action": "sweeper.escalated",
                "patient": pid,
                "dose": dose,
                "date": d.isoformat(),
                "age_min": age_min,
                "nurse_chat": config.NURSE_CHAT_ID,
            }
        )
