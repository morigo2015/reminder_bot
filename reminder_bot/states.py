from aiogram.fsm.state import State, StatesGroup

class ReminderStates(StatesGroup):
    waiting_confirmation = State()
    waiting_clarification = State()
    entering_pressure = State()
    collecting_status = State()
