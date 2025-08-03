from aiogram import Router
from aiogram.types import Message

router = Router()

@router.message()
async def unknown(message: Message):
    await message.answer("Sorry, I didn't understand that. Please reply with the code you were reminded about.")
