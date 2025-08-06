from services.config import config
from aiogram import Bot

async def escalate_to_nurse(chat_id: int, event_key: str, bot: Bot):
    nurse_id = config.get("nurse_chat_id")
    text = config["messages"]["nurse_alert"].format(chat_id=chat_id, event_key=event_key)
    await bot.send_message(nurse_id, text)
