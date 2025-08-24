# -*- coding: utf-8 -*-
from typing import Mapping

T = {
    # Pills – patient
    "pills.initial": "Час випити ліки 💊 {label}\n\nБудь ласка, натисніть кнопку 'Підтвердити прийом' ПІСЛЯ того як приймете ліки",
    "pills.repeat": "🔔 Повторне нагадування 💊 {label}\n\n❗ Не забудьте підтвердити!",
    "pills.final": "⚠️ Не отримано підтвердження що ліки прийнято.\n\nВідправляю повідомлення Ірі 👩‍⚕️.",
    "pills.confirm_ack": "✅ Дякую! 🙏\n\n💊 Прийом ліків ({label}) підтверджено ✅\n\nГарного дня! 😊",
    # Pills – nurse (private chat)
    "pills.escalation": (
        "🚨 Увага: {name} не підтвердила прийом ліків {label}.\n"
        "Було заплановано на {time_local}\n⏱️ Вже минуло: {minutes} хв."
    ),
    "pills.late_confirm": (
        "ℹ️ Оновлення: {name} підтвердила прийом ліків {label} (вже ПІСЛЯ ескалації).\n"
    ),
    # BP
    "bp.reminder": (
        "🩺 Час виміряти тиск! 🩺\n\n"
        "📝 Будь ласка, виміряйте тиск на обох руках.\n\n"
        "💬 Надішліть у форматі:\n"
        "👈 'left 120/80 70' або\n"
        "👉 'right 125/82 72'"
    ),
    "bp.error.format": "❌ Невірні значення.\n\n📝 Приклад: right 125/82 72",
    "bp.error.range": "⚠️ Поза межами діапазону.\n\n🔄 Перевірте, будь ласка, і надішліть ще раз.",
    "bp.out_of_range_nurse": (
        "⚠️ Попередження: у пацієнта {name} тиск поза межами:\n"
        "📍 {side}, {sys}/{dia}, пульс {pulse}"
    ),
    # Status
    "status.prompt": "😊 Як Ви сьогодні себе почуваєте?\n\n💭 Коротко опишіть стан.",
    "status.alert_nurse": (
        "🚨 Попередження: стан пацієнта {name} містить ризикові ознаки:\n⚠️ '{match}'"
    ),
    # Generic
    "generic.not_found_pending": (
        "ℹ️ Немає нагадувань, що очікують підтвердження.\n\n"
        "💊 Якщо Ви вже прийняли ліки,\n"
        "👆 будь ласка, натисніть кнопку під відповідним повідомленням."
    ),
}


class MissingVarError(KeyError): ...


def render(key: str, **vars: Mapping[str, object]) -> str:
    try:
        return T[key].format(**vars)
    except KeyError as e:
        raise MissingVarError(f"Template '{key}' missing var: {e}") from e
