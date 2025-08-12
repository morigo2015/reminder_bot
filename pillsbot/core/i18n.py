from __future__ import annotations

MESSAGES = {
    # v1 pill-reminder texts (unchanged)
    "reminder": "час прийняти {pill_text}",
    "repeat_reminder": "не отримано підтвердження",
    "confirm_ack": "підтвердження прийнято, дякую",
    "preconfirm_ack": "заздалегідь - теж ОК. Дякую",
    "too_early": "ще не на часі, чекайте нагадування",
    "escalate_group": "не отримано підтвердження, залучаємо мед.сестру",
    "escalate_dm": "пацієнт ({patient_label}): пропустив {date} {time}, {pill_text}",
    # v2 measurement acks/errors + daily check
    "measure_ack": "отримано показник {measure_label}. Все ок.",
    "measure_error_arity": "вибачте, помилка. має бути {expected} числа",
    "measure_error_one": "вибачте, помилка. має бути 1 число",
    "measure_unknown": "вибачте, помилка. невідомий показник",
    "measure_missing_today": "сьогодні не отримано показник {measure_label}",
    # v3 buttons / prompts / help
    "btn_pressure": "Тиск",
    "btn_weight": "Вага",
    "btn_help": "Help",
    "btn_confirm_taken": "Ліки вже прийнято",
    "prompt_pressure": 'Введіть три числа: систолічний, діастолічний, пульс. Приклад: "тиск 120 80 60".',
    "prompt_weight": 'Введіть одну цифру (кг). Приклад: "вага 72,5".',
    "help_brief": (
        "Кнопки:\n"
        '• Тиск — надішліть 3 числа: верхній, нижній, пульс (наприклад: "тиск 120 80 60").\n'
        '• Вага — надішліть одне число в кг (наприклад: "вага 72,5").\n'
        "• Ліки вже прийнято — підтвердження прийому.\n"
        'Також можна просто написати: "ок", "+", "так" тощо.'
    ),
    # v3 callback responses / guards
    "cb_only_patient": "Ця кнопка — лише для пацієнта.",
    "cb_already_done": "Це нагадування вже підтверджено. Дякую!",
    "cb_late_ok": "Підтверджено. Дякую!",
    "cb_no_target": "Немає активного нагадування.",
}


def fmt(key: str, **kwargs) -> str:
    return MESSAGES[key].format(**kwargs)
