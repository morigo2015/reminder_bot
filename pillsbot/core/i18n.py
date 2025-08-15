from __future__ import annotations

# v4 message catalog (UA; concise, Option A)

MESSAGES = {
    # Menu texts
    "reminder_text": "Час прийняти ліки. Підтвердіть прийом або оберіть дію нижче.",
    "idle_text": "Що зробимо? Оберіть дію нижче.",

    # Buttons
    "btn_confirm_taken": "Ліки вже прийнято",
    "btn_pressure": "Тиск",
    "btn_weight": "Вага",
    "btn_help": "Help",

    # Prompts / Help
    "prompt_pressure": "Надішліть 120/80 [пульс].",
    "prompt_weight": "Надішліть вагу, напр.: 72.5 (можна 72 або 72,5; «кг» — за бажанням).",
    "help_text": (
        "Як надіслати показник:\n"
        "• Тиск: 120/80 [пульс] — приклади: 120/80 72 • 120 80 • 120-80 • 120 на 80\n"
        "• Вага: 72.5 — можна 72 або 72,5 (з «кг» чи без)\n\n"
        "Порада: після натискання кнопки просто надішліть числа — без слів."
    ),

    # Acks
    "ack_confirm": "Готово! Зафіксовано, що ліки прийнято.",
    "ack_pressure": "Готово! Записав тиск {systolic}/{diastolic}.",
    "ack_pressure_pulse": "Готово! Записав тиск {systolic}/{diastolic}, пульс {pulse}.",
    "ack_weight": "Готово! Записав вагу {kg} кг.",

    # Parse errors — pressure
    "err_pressure_one": "Очікую два або три числа для тиску. Приклад: 120/80 [72]",
    "err_pressure_range": (
        "Схоже, це нереальні значення для тиску. "
        "Приклад: 120/80 [72] (систолічний 70–250, діастолічний 40–150, пульс 30–220)."
    ),
    "err_pressure_unrec": "Не вдалося розпізнати тиск. Приклади: 120/80 • 120 80 • 120-80 [72]",

    # Parse errors — weight
    "err_weight_likely_pressure": "Схоже, це тиск (два числа). Для ваги надішліть одне число, напр.: 72.5",
    "err_weight_range": "Схоже, нереальна вага. Приклад: 72.5 (припустимий діапазон: 25–300 кг)",
    "err_weight_unrec": "Не вдалося розпізнати вагу. Надішліть лише цифри, напр.: 72.5",

    # Fallback for unknown text
    "unknown_text": "Не вдалося розпізнати повідомлення. Оберіть дію нижче.",

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
