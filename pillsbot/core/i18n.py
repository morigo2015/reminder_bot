from __future__ import annotations

# v4 message catalog (UA; concise)

MESSAGES = {
    # Menu texts
    "reminder_text": "Час прийняти ліки. Підтвердіть прийом або оберіть дію нижче.",
    "idle_text": "Що зробимо? Оберіть дію нижче.",
    # Buttons
    "btn_confirm_taken": "Ліки вже прийнято",
    "btn_pressure": "Тиск",
    "btn_weight": "Вага",
    "btn_help": "Допомога",
    # Prompts / Help
    "prompt_pressure": "Надішліть тиск у форматі 120/80",
    "prompt_weight": "Надішліть вагу у кілограмах (наприклад 72.5)",
    "help_text": "Тут можна підтвердити прийом ліків, надіслати тиск або вагу.",
    # Acks
    "ack_confirm": "Готово! Зафіксовано, що ліки прийнято.",
    "ack_pressure": "Записав тиск {systolic}/{diastolic}.",
    "ack_weight": "Записав вагу {kg} кг.",
    # Parse errors
    "err_pressure": "Не вдалося розпізнати тиск. Приклад: 120/80",
    "err_weight": "Не вдалося розпізнати вагу. Приклад: 72.5",
    # Fallback for unknown text
    "unknown_text": "Не розпізнав. Спробуйте кнопки нижче.",
    # Nurse late confirm notification (unchanged semantics)
    "nurse_late_confirm_dm": (
        "пацієнт ({patient_label}) підтвердив прийом ПІСЛЯ ескалації: "
        "{date} {time}, {pill_text}"
    ),
    # Escalation group/nurse texts (kept for retry flow)
    "escalate_group": "не отримано підтвердження, залучаємо мед.сестру",
    "escalate_dm": "пацієнт ({patient_label}): пропустив {date} {time}, {pill_text}",
}


def fmt(key: str, **kwargs) -> str:
    return MESSAGES[key].format(**kwargs)
