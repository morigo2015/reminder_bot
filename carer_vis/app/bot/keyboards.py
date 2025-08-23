from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BUTTON_TEXT_CONFIRM = "Підтвердити прийом ✅"


def confirm_keyboard(callback_payload: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BUTTON_TEXT_CONFIRM, callback_data=callback_payload)]]
    )
