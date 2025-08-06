from aiogram.fsm.state import StatesGroup, State

class ReminderStates(StatesGroup):
    waiting_confirmation = State()
    waiting_clarification = State()

class StatusFlow(StatesGroup):
    waiting_status = State()
