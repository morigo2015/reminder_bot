import re
from aiogram import Router, F
from aiogram.types import Message
from services.logging import CSVLogger

router = Router()
pressure_logger = CSVLogger("pressure")
bp_regex = re.compile(r"^\D*(\d{2,3})[ /,-](\d{2,3})[ /,-](\d{2,3})\D*$")

@router.message(F.text.regexp(bp_regex))
async def pressure_handler(message: Message):
    match = bp_regex.match(message.text)
    if not match:
        return
    systolic, diastolic, pulse = match.groups()
    await pressure_logger.log(message.chat.id, systolic=systolic, diastolic=diastolic, pulse=pulse)
    await message.reply("Дякую, тиск записано.")
