# -*- coding: utf-8 -*-
from typing import Mapping

T = {
    # Pills – patient
    "pills.initial": "Час випити ліки з коробки: {label}",
    "pills.repeat": "Повторно нагадую: час випити ліки ({label})",
    "pills.final": "Не отримано підтвердження. Долучаю медсестру.",
    "pills.confirm_ack": "Дякую! Прийом ліків ({label}) підтверджено ✅",
    # Pills – nurse (private chat)
    "pills.escalation": (
        "Ескалація: пацієнт {name} не підтвердив прийом ліків.\n"
        "Доза: {label} (план — {time_local})\nМинуло: {minutes} хв."
    ),
    "pills.late_confirm": (
        "Оновлення: пацієнт {name} підтвердив прийом ліків ПІСЛЯ ескалації.\n"
        "Доза: {label} (план — {time_local})"
    ),
    # BP
    "bp.reminder": (
        "Будь ласка, виміряйте тиск на обох руках.\n"
        'Надішліть у форматі: "left 120/80 70" або "right 125/82 72".'
    ),
    "bp.error.format": "Невірні значення. Приклад: right 125/82 72",
    "bp.error.range": "Поза межами діапазону. Перевірте, будь ласка, і надішліть ще раз.",
    "bp.out_of_range_nurse": (
        "Попередження: у пацієнта {name} тиск поза межами: {side}, {sys}/{dia}, пульс {pulse}."
    ),
    # Status
    "status.prompt": "Як Ви сьогодні себе почуваєте? Коротко опишіть стан.",
    "status.alert_nurse": (
        'Попередження: стан пацієнта {name} містить ризикові ознаки: "{match}".'
    ),
    # Generic
    "generic.not_found_pending": (
        "Немає нагадувань, що очікують підтвердження. Якщо Ви вже прийняли ліки, \n"
        "будь ласка, натисніть кнопку під відповідним повідомленням."
    ),
}


class MissingVarError(KeyError): ...


def render(key: str, **vars: Mapping[str, object]) -> str:
    try:
        return T[key].format(**vars)
    except KeyError as e:
        raise MissingVarError(f"Template '{key}' missing var: {e}") from e
