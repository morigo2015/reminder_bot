# -*- coding: utf-8 -*-
from typing import Mapping

T = {
    # Pills – patient
    "pills.initial": "🔔💊 Час випити ліки <b>{label}</b>\n\n❗Натисніть\n'Підтвердити прийом'\n <b>ПІСЛЯ</b> того як приймете ліки",
    "pills.repeat": "🔔💊 Повторне нагадування: ліки <b>{label}</b>\n\n❗ Не забудьте підтвердити!",
    "pills.final": "⚠️💊 Підтвердження так і <b>не отримано</b>❗\n🚨 Відправляю повідомлення Ірині!",
    "pills.confirm_ack": "✅💊 Дякую!\nПрийом <b>{label}</b> підтверджено",
    # Pills – nurse (private chat)
    "pills.escalation": (
        "🚨💊 Увага: {name} не підтвердила прийом ліків <b>{label}</b>.\n"
        "Було заплановано на {time_local}\n⏱️ Вже минуло: {minutes} хв."
    ),
    "pills.late_confirm": (
        "ℹ️ Оновлення: {name} підтвердила прийом ліків <b>{label}</b> (вже ПІСЛЯ ескалації).\n"
    ),
    # BP
    "bp.reminder": "🔔💓 Час виміряти тиск!\n\nНадішліть результати у форматі:\nпапа 120 60 55\nабо:\nмама 120 60 55",
    "bp.error.format": "❌💓🔄 Невірно записані результати тиску\n\nПриклад як правильно: папа 120 60 55",
    "bp.error.range": "⚠️💓🔄 Значення тиску - поза межами.\n\n Перевірте, будь ласка, і надішліть ще раз.",
    "bp.out_of_range_nurse": "🚨💓 Попередження: у {side} тиск поза межами:\n {sys}/{dia} {pulse}",
    "bp.received_ack": "✅💓 Отримано виміри тиску \n {side}: {sys}/{dia} {pulse}\nДякую!",
    # Status
    "status.prompt": "😊 Як Ви сьогодні себе почуваєте?\n\n💭 Коротко опишіть стан.",
    "status.alert_nurse": (
        "🚨 Попередження: стан пацієнта {name} містить ризикові ознаки:\n⚠️ '{match}'"
    ),
    "message.unknown": "отримано:\n<b>{received_message}</b>\n🤷🏼‍♂️не розумію що це.",
}


class MissingVarError(KeyError): ...


def render(key: str, **vars: Mapping[str, object]) -> str:
    try:
        return T[key].format(**vars)
    except KeyError as e:
        raise MissingVarError(f"Template '{key}' missing var: {e}") from e
