# app/prompts.py
from __future__ import annotations

from datetime import datetime

from . import config
from .utils import format_kyiv


# ---- Pill prompts ----
def med_due(name: str, label_daypart: str) -> str:
    return f"{name}, час прийняти ліки ({label_daypart}). Підтвердіть, будь ласка."


def med_nag(name: str) -> str:
    return f"{name}, нагадування: підтвердіть, будь ласка, що ви прийняли ліки."


def med_escalate_to_caregiver(patient_name: str, due_at: datetime) -> str:
    return f"Ескалація: {patient_name} не підтвердив(ла) прийом ліків (на {format_kyiv(due_at)})."


def ok_ack() -> str:
    return "Дякую, зафіксовано ✅"


def sorry_ack() -> str:
    return "Добре, зафіксував(ла) ❎"


# ---- BP prompts ----
def measure_bp_due(name: str) -> str:
    return f"{name}, час виміряти тиск сьогодні. Відправте «систолічний, діастолічний, пульс»."


def clarify_bp() -> str:
    return "Не бачу трьох чисел для тиску. Відправте, будь ласка: «систолічний, діастолічний, пульс»."


def clarify_nag() -> str:
    return "Нагадування: надішліть три числа тиску, будь ласка."


def bp_recorded_ack(syst: int, diast: int, pulse: int) -> str:
    return f"Записав(ла) тиск: {syst}/{diast}, пульс {pulse}."


def bp_escalate_to_caregiver(patient_name: str) -> str:
    return f"Ескалація: {patient_name} не надіслав(ла) коректні дані тиску."


# ---- Group moderation ----
def only_patient_can_write() -> str:
    # fixed wording: "цю групу"
    return "Будь ласка, не пишіть у цю групу. Тут спілкуються лише пацієнт і бот."


# ---- Misc helpers ----
def label_daypart(threshold_hhmm: str, when: datetime) -> str:
    hhmm = when.astimezone(config.TZ).strftime("%H:%M")
    return "ранок" if hhmm < threshold_hhmm else "вечір"
