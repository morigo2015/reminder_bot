# app/prompts.py
# Centralized UA strings (PoC). Matches Specs v2.1.

from __future__ import annotations
from datetime import datetime
from . import config


# ---------- Group moderation ----------
def only_patient_can_write(patient_name: str) -> str:
    return f"Тільки {patient_name} може надсилати повідомлення в цю группу"


# ---------- Pills ----------
def pill_prompt(patient_name: str, label: str) -> str:
    return f'Час прийняти ліки "{label}".'


def pill_nag(label: str) -> str:
    return f'Нагадую: треба прийняти ліки "{label}".'


def pill_escalation(patient_name: str, due_dt: datetime, label: str) -> str:
    due_str = due_dt.astimezone(config.TZ).strftime(config.DATETIME_FMT)
    return f'Пацієнт {patient_name} пропустив прийом ліків, запланований на {due_str}. Мітка: "{label}".'


def med_taken_photo_ack() -> str:
    return "Дякую за фото. Запишу як прийнято."


def med_taken_followup() -> str:
    return "Чудово. Дякую."


def ask_clarify_yes_no() -> str:
    return "Не розчула. Ви прийняли ліки? (так/ні)"


def voice_kindly_decline() -> str:
    return "Будь ласка, напишіть коротко текстом."


# ---------- Blood Pressure ----------
def measure_bp_prompt(patient_name: str) -> str:
    return (
        f"{patient_name}, виміряйте тиск і пульс.\n"
        f"Напишіть: <тип> <систолічний> <діастолічний> <пульс>.\n"
        f"Напр.: швидко 125 62 51."
    )


def bp_clarify_missing_type() -> str:
    return (
        "Я не бачу тип вимірювання. Будь ласка, додайте його: "
        "<тип> <систолічний> <діастолічний> <пульс>. "
        "Напр.: швидко 125 62 51."
    )


def bp_clarify_two_numbers() -> str:
    return (
        "Потрібно три числа (тиск систолічний, діастолічний і пульс) та тип. "
        "Напр.: довго 127 61 52."
    )


def bp_clarify_unknown_type(canonical_types: list[str]) -> str:
    opts = ", ".join(canonical_types)
    return f"Не розпізнав(ла) тип. Доступні: {opts}. Напр.: швидко 125 62 51."


def bp_clarify_bad_order() -> str:
    return "Тип має бути на початку або в кінці. Приклад: швидко 125 62 51."


def bp_clarify_nag() -> str:
    return "Нагадую: надішліть, будь ласка, <тип> <систолічний> <діастолічний> <пульс>."


def bp_out_of_range_alert(
    patient_name: str, sys: int, dia: int, pulse: int, bp_type: str
) -> str:
    return (
        f'Алерт: {patient_name} повідомив(ла) АТ {sys}/{dia}, пульс {pulse}, тип "{bp_type}". '
        f"За межами належних меж."
    )


# Generic
def ok_ack() -> str:
    return "Гаразд."


def sorry_ack() -> str:
    return "Розумію."
