"""Escalation handling – ping the nurse when a patient does not confirm."""

from aiogram import Bot
from reminder_bot.utils import logging as log
from reminder_bot.config import NURSE_CHAT_ID


async def escalate(bot: Bot, event_name: str, patient_chat_id: int) -> None:
    if NURSE_CHAT_ID == 0:
        # Nurse not configured – just log.
        log.log(event_name, patient_chat_id, "ESCALATION_ERROR", 0)
        return
    try:
        await bot.send_message(
            chat_id=NURSE_CHAT_ID,
            text=f"⚠️ Patient {patient_chat_id} did not confirm '{event_name}'.",
        )
        log.log(event_name, patient_chat_id, "ESCALATED", 0)
    except Exception as exc:  # pragma: no cover
        log.log(event_name, patient_chat_id, f"ESCALATION_ERROR:{exc}", 0)
