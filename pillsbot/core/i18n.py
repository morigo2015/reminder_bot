from __future__ import annotations

MESSAGES = {
    "reminder": "час прийняти {pill_text}",
    "repeat_reminder": "не отримано підтвердження",
    "confirm_ack": "підтвердження прийнято, дякую",
    "preconfirm_ack": "заздалегідь - теж ОК. Дякую",
    "too_early": "ще не на часі, чекайте нагадування",
    "escalate_group": "не отримано підтвердження, залучаємо мед.сестру",
    "escalate_dm": "пацієнт ({patient_label}): пропустив {date} {time}, {pill_text}",
}

def fmt(key: str, **kwargs) -> str:
    return MESSAGES[key].format(**kwargs)
