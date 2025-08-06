import re
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from reminder_bot.states import ReminderStates

router = Router()

PRESSURE_CMD_PATTERN = re.compile(r'^(?:/pressure|/bp)$', re.IGNORECASE)
PRESSURE_PATTERN = re.compile(r'^(?:тиск|pressure)\s+(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})$', re.IGNORECASE)

@router.message()
async def pressure_entry(message: Message, state: FSMContext):
    text = message.text or ''
    if PRESSURE_CMD_PATTERN.match(text):
        await message.answer('Введіть три числа: систолічний, діастолічний, пульс, наприклад: тиск 120 80 70')
        await state.set_state(ReminderStates.entering_pressure)
        return
    # If in entering_pressure state, try to match numbers
    current_state = await state.get_state()
    if current_state == ReminderStates.entering_pressure:
        m = PRESSURE_PATTERN.match(text)
        if not m:
            await message.answer('Невірний формат. Введіть, будь ласка, три числа, наприклад: тиск 120 80 70')
            return
        high, low, pulse = map(int, m.groups())
        log_service = message.bot['log_service']
        await log_service.pressure(message.chat.id, high, low, pulse)
        await message.answer(f'📋 Logged pressure: {high}/{low}, pulse {pulse}')
        await state.clear()
