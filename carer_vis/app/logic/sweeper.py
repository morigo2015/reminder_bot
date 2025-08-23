# app/logic/sweeper.py
"""
Minimal sweeper for overdue pill confirmations.

Policy:
  - Escalate ONLY rows that actually exist in the DB (i.e., an initial was sent).
  - A row is eligible when age_min >= confirm_window_min for that patient.
  - Never synthesize "overdue" from schedule alone (no backfill, no activation tracking).
  - Mark the row as escalated in DB to prevent duplicate escalations.

Assumptions:
  - DB layer (app.db.pills) exposes:
      - overdue_candidates() -> list[tuple(patient_id, date_kyiv, dose, age_min)]
        (only rows with reminder_ts IS NOT NULL, confirm_ts IS NULL, escalated_ts IS NULL)
      - mark_escalated(patient_id, date_kyiv, dose) -> bool
  - time helpers provide local labels (pill_label).
  - texts_uk provides localized copy. If you don't have a dedicated key for escalation,
    you can adjust the message below or add `pills.escalation` to your copy.
"""

from __future__ import annotations

from typing import Optional
from aiogram import Bot

from app import config
from app.bot import texts_uk
from app.db import pills
from app.util import timez


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


def _escalation_chat_id(patient: dict) -> int:
    # Prefer a global escalation sink if configured; fall back to the patient's chat.
    chat_id = getattr(config, "ESCALATION_CHAT_ID", None)
    return chat_id if chat_id is not None else int(patient["chat_id"])


async def sweep(bot: Bot) -> None:
    """
    Runs periodically (see SWEEP_SECONDS in main.py).
    Escalates unconfirmed reminders that are past the confirmation window.
    """
    # Each row: (patient_id, date_kyiv, dose, age_min)
    rows = await pills.overdue_candidates()

    for pid, d, dose, age_min in rows:
        patient = _find_patient(pid)
        if not patient:
            # Unknown patient id in DB; skip.
            print(
                {"level": "warn", "action": "sweeper.skip.unknown_patient", "pid": pid}
            )
            continue

        window_min = _confirm_window_min(patient)

        # Only escalate when the age exceeds (or equals) the confirmation window.
        if age_min < window_min:
            # Not yet overdue by policy; skip.
            continue

        # Mark escalated in DB first (idempotency). If we win the race, we send.
        updated = await pills.mark_escalated(pid, d, dose)
        if not updated:
            # Someone else escalated or state changed; skip.
            continue

        # Compose message.
        label = timez.pill_label(dose, d)
        try:
            # If you have a dedicated key, prefer it.
            text = texts_uk.render("pills.escalation", label=label, age_min=age_min)
        except Exception:
            # Fallback plain text (keeps the function robust if the key is missing).
            text = f"⚠️ Немає підтвердження прийому: {label} (затримка {age_min} хв)."

        # Decide chat to notify: global escalation sink if present, else the patient.
        chat_id = _escalation_chat_id(patient)

        # Fire-and-forget send; let the outer loop's try/except in main handle crashes if any.
        try:
            await bot.send_message(chat_id, text)
            print(
                {
                    "level": "info",
                    "action": "sweeper.escalated",
                    "patient": pid,
                    "dose": dose,
                    "date": d.isoformat(),
                    "age_min": age_min,
                    "chat_id": chat_id,
                }
            )
        except Exception as e:
            # We already marked escalated in DB to avoid loops; just log the error.
            print(
                {
                    "level": "error",
                    "action": "sweeper.send_error",
                    "patient": pid,
                    "dose": dose,
                    "date": d.isoformat(),
                    "exception": str(e),
                }
            )
