from aiogram import Router, F
from aiogram.types import Message, Chat, User
from aiogram.filters.command import Command
from services.scheduler import schedule_once, dispatcher
from services.logging import CSVLogger
from services.config import config
from states import StatusFlow
from aiogram.fsm.context import FSMContext

router = Router()
status_logger = CSVLogger("status")

@router.message(Command("status"))
async def status_start(message: Message):
    state = FSMContext(storage=dispatcher.storage, chat=message.chat, user=message.from_user)
    await state.set_state(StatusFlow.waiting_status)
    await state.update_data(messages=[])
    await message.reply("Будь ласка, опишіть свій стан протягом 5 хвилин.")
    schedule_once(message.chat.id, "status_window", config["status_window_sec"], status_end_handler)

async def status_end_handler(job):
    chat_id = job.data["chat_id"]
    bot = job.bot
    fsm_ctx = FSMContext(storage=dispatcher.storage, chat=Chat(id=chat_id, type="private"), user=User(id=chat_id, is_bot=False))
    data = await fsm_ctx.get_data()
    messages = data.get("messages", [])
    await status_logger.log(chat_id, messages=" | ".join(messages))
    await fsm_ctx.clear()
    await bot.send_message(chat_id, "Дякую за інформацію. Завершуємо статус.")

@router.message(StatusFlow.waiting_status, F.text)
async def collect_status(message: Message):
    state = FSMContext(storage=dispatcher.storage, chat=message.chat, user=message.from_user)
    data = await state.get_data()
    msgs = data.get("messages", [])
    msgs.append(message.text)
    await state.update_data(messages=msgs)
