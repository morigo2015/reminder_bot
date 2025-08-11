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
}


def fmt(key: str, **kwargs) -> str:
    return MESSAGES[key].format(**kwargs)
