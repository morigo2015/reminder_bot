from __future__ import annotations

"""
i18n catalog.

This file preserves v4 keys and adds v5 keys + any keys used by the v4 engine
(e.g., ack_confirm, prompt_pressure, prompt_weight).
"""

MESSAGES = {
    # Menu texts (technical/idle)
    "reminder_text": "Час прийняти ліки. Підтвердіть прийом або оберіть дію нижче.",
    "idle_text": "Що зробимо? Оберіть дію нижче.",
    # Buttons
    "btn_confirm_taken": "Ліки вже прийнято",
    "btn_pressure": "Тиск",
    "btn_weight": "Вага",
    "btn_help": "Help",
    # Prompts / Help
    "help_text": (
        "Ви можете підтвердити прийом ліків кнопкою нижче або текстом.\n"
        "Доступні вимірювання: тиск, вага."
    ),
    # Contentful group lines
    "reminder_line": "Час прийняти ліки: {pill_text}",
    # Nurse DMs (existing)
    "escalate_dm": "пацієнт ({patient_label}): пропустив {date} {time}, {pill_text}",
    "nurse_late_confirm_dm": (
        "пацієнт ({patient_label}) підтвердив прийом ПІСЛЯ ескалації: "
        "{date} {time}, {pill_text}"
    ),
    # Engine-required (restored)
    "ack_confirm": "Готово! Прийом зафіксовано.",
    "ack_pressure": "Записав тиск {systolic}/{diastolic}.",
    "ack_pressure_pulse": "Записав тиск {systolic}/{diastolic}, пульс {pulse}.",
    "unknown_text": "Не вдалося розпізнати це повідомлення.",
    "prompt_pressure": "Будь ласка, надішліть вимір тиску у форматі «120/80».",
    "prompt_weight": "Будь ласка, надішліть вагу у кілограмах (наприклад, 72.4).",
}

# v5 additions
MESSAGES.update(
    {
        "reminder_retry_prefix": "Нагадування {n}: ",
        "escalate_group": "Пропущено прийом ліків!!! Повідомлення відправлено медичній медичній сестрі".replace(
            " медичній медичній", " медичній"
        ),  # guard against accidental dup
        "startup_greeting": "Всім доброго дня!",
    }
)


def fmt(key: str, **kwargs) -> str:
    return MESSAGES[key].format(**kwargs)
