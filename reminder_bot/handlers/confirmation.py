import re
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from reminder_bot.states import ReminderStates

router = Router()

OK_PATTERN = re.compile(r'^(?:ok|так|yes|si|sure|👍)$', re.IGNORECASE)

@router.message(ReminderStates.waiting_confirmation)
async def handle_confirmation(message: Message, state: FSMContext):
    text = message.text or ''
    if not OK_PATTERN.match(text):
        return
    data = await state.get_data()
    event = data.get('current_event')
    manager = message.bot['reminder_manager']
    await manager.cancel_flow(event, message.chat.id)
    await message.answer('✅ Confirmed.')
    await state.clear()

@router.message(ReminderStates.waiting_clarification)
async def handle_clarification(message: Message, state: FSMContext):
    text = message.text or ''
    if not OK_PATTERN.match(text):
        return
    data = await state.get_data()
    event = data.get('current_event')
    manager = message.bot['reminder_manager']
    await manager.finalize_flow(event, message.chat.id)
    await message.answer('✅ Clarification received.')
    await state.clear()
