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


def med_confirmed_with_label(label: str) -> str:
    return f"Прийом ліків {label} підтверджено ✅"


def patient_missed_pill_notice(label: str) -> str:
    return f"Пропущено прийом ліків {label}!! Інформую медичну сестру."


def caregiver_confirmed_after_escalation(patient_name: str, label: str) -> str:
    return f"Оновлення: {patient_name} підтвердив(ла) прийом ліків {label} після ескалації."


# ---- Simple acks ----
def ok_ack() -> str:
    return "Дякую, зафіксовано ✅"


def sorry_ack() -> str:
    return "Добре, зафіксував(ла) ❎"


# ---- BP prompts ----
def measure_bp_due(name: str) -> str:
    return f"{name}, час виміряти тиск сьогодні. Відправте «тип сис діа пульс», напр.: «швидко 120 80 60»."


def clarify_bp() -> str:
    return "Не бачу коректного повідомлення про тиск. Формат: «тип сис діа пульс»."


def clarify_nag() -> str:
    return "Нагадування: надішліть тиск у форматі «тип сис діа пульс», напр.: «швидко 120 80 60»."


def bp_recorded_ack(syst: int, diast: int, pulse: int) -> str:
    return f"Записав(ла) тиск: {syst}/{diast}, пульс {pulse}."


def bp_recorded_ack_with_label(label: str, syst: int, diast: int, pulse: int) -> str:
    return f"Тиск {label} : {syst} {diast} {pulse} записано."


def bp_recorded_ack_with_type(bp_type: str, syst: int, diast: int, pulse: int) -> str:
    return f"Тиск {bp_type} : {syst} {diast} {pulse} записано."


def bp_need_type_retry() -> str:
    return (
        "Будь ласка, надішліть тиск з типом: «тип сис діа пульс».\n"
        "Приклади: «швидко 120 80 60», «повільно 118 76 58»."
    )


def bp_escalate_to_caregiver(patient_name: str) -> str:
    # Added back to fix escalation crash in BP clarify flow
    return f"Ескалація: {patient_name} не надіслав(ла) коректні дані тиску."


# ---- Group moderation ----
def only_patient_can_write() -> str:
    # fixed wording: "цю групу"
    return "Будь ласка, не пишіть у цю групу. Тут спілкуються лише пацієнт і бот."


# ---- Misc helpers ----
def label_daypart(threshold_hhmm: str, when: datetime) -> str:
    hhmm = when.astimezone(config.TZ).strftime("%H:%M")
    return "ранок" if hhmm < threshold_hhmm else "вечір"
