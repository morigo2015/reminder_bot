from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from states import ReminderStates
from services.log_service import LogService

router = Router()
log_service = LogService()


@router.message(F.text.startswith("/pressure") | F.text.startswith("/bp"))
async def pressure_entry(message: Message, state: FSMContext):
    """
    Starts the blood-pressure entry flow.
    """
    await state.set_state(ReminderStates.entering_pressure)
    await message.reply(
        "Please enter your blood pressure as systolic/diastolic (e.g. 120/80):"
    )


@router.message(ReminderStates.entering_pressure)
async def pressure_record(message: Message, state: FSMContext):
    """
    Records the pressure reading and clears state.
    """
    text = message.text.strip()
    # Basic parse: "120/80"
    try:
        systolic, diastolic = map(int, text.split("/"))
    except ValueError:
        return await message.reply(
            "Invalid format. Please use systolic/diastolic (e.g. 120/80)."
        )

    # Log the values
    await log_service.pressure(
        chat_id=message.chat.id, systolic=systolic, diastolic=diastolic
    )
    await message.reply(f"Logged your blood pressure: {systolic}/{diastolic}. Thanks!")
    await state.clear()
