# app/prompts.py
# Centralized UA strings (PoC). Later these functions map 1:1 to i18n/Jinja templates.

def med_due(patient_name: str, med_name: str, dose: str) -> str:
    return f"{patient_name}, час прийняти {med_name} — {dose}. Напишіть «прийняв/прийняла» або надішліть фото."

def med_reprompt(med_name: str) -> str:
    return f"Нагадую про {med_name}. Потрібна допомога?"

def med_taken_followup() -> str:
    return "Чудово. Чи не було побічних ефектів? (так/ні)"

def med_taken_photo_ack() -> str:
    return "Дякую за фото. Запишу як прийнято."

def med_missed_escalate(patient_name: str, med_name: str, due_time_local: str) -> str:
    # Message for caregiver group
    return f"⚠️ Пропуск дози. Пацієнт: {patient_name}. Препарат: {med_name}. Час за розкладом: {due_time_local}."

def ask_clarify_yes_no() -> str:
    return "Не розчула. Ви прийняли ліки? (так/ні)"

def voice_kindly_decline() -> str:
    return "Будь ласка, напишіть коротко текстом."

# Measurements
def measure_bp_prompt(patient_name: str) -> str:
    return f"{patient_name}, виміряйте тиск і надішліть, наприклад: 130/85."

def measure_temp_prompt(patient_name: str) -> str:
    return f"{patient_name}, виміряйте температуру і надішліть число, наприклад: 37.2."

def measure_recorded_ack() -> str:
    return "Дякую. Записала."

def high_bp_alert(patient_name: str, systolic: int, diastolic: int) -> str:
    return f"⚠️ Високий тиск у {patient_name}: {systolic}/{diastolic}. Рекомендую звернутися до лікаря. Повідомляю опікуна."

def high_temp_alert(patient_name: str, temp_c: float) -> str:
    return f"⚠️ Висока температура у {patient_name}: {temp_c:.1f}°C. Рекомендую звернутися до лікаря. Повідомляю опікуна."

# Caregiver notifications
def caregiver_high_bp(patient_name: str, systolic: int, diastolic: int) -> str:
    return f"🚑 Тиск: {patient_name} — {systolic}/{diastolic}."

def caregiver_high_temp(patient_name: str, temp_c: float) -> str:
    return f"🚑 Температура: {patient_name} — {temp_c:.1f}°C."

def caregiver_forward_unknown(patient_name: str, last_text: str) -> str:
    preview = (last_text[:120] + "…") if len(last_text) > 120 else last_text
    return f"ℹ️ Невизначене повідомлення від {patient_name}: «{preview}»"

# Generic
def ok_ack() -> str:
    return "Гаразд."

def sorry_ack() -> str:
    return "Розумію."
