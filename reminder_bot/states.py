from aiogram.fsm.state import StatesGroup, State


class ReminderStates(StatesGroup):
    waiting_confirmation = State()
    waiting_clarification = State()
    entering_pressure = State()
