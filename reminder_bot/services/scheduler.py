from datetime import time as dt_time
from aiogram import Dispatcher
from aiogram.types import Chat, User
from aiogram.fsm.context import FSMContext
from states import ReminderFlow, StatusFlow
from services.config import config

job_queue = None
dispatcher = None

def init_scheduler(dp: Dispatcher):
    global job_queue, dispatcher
    dispatcher = dp
    job_queue = dp.job_queue

def schedule_once(chat_id: int, name: str, delay: float, callback, job_data: dict = None):
    data = {"chat_id": chat_id}
    if job_data:
        data.update(job_data)
    job_queue.run_once(callback, delay, data=data, name=f"{chat_id}:{name}")

def schedule_daily(chat_id: int, name: str, time_str: str, callback, job_data: dict = None):
    hh, mm = map(int, time_str.split(":"))
    when = dt_time(hour=hh, minute=mm)
    data = {"chat_id": chat_id}
    if job_data:
        data.update(job_data)
    job_queue.run_daily(callback, when, data=data, name=f"{chat_id}:{name}")

def cancel_jobs(chat_id: int, prefix: str):
    for job in list(job_queue.get_jobs()):
        if job.name and job.name.startswith(f"{chat_id}:{prefix}"):
            job.schedule_removal()

async def _start_fsm(chat_id: int, event_key: str, state):
    chat = Chat(id=chat_id, type="private")
    user = User(id=chat_id, is_bot=False)
    fsm_ctx = FSMContext(storage=dispatcher.storage, chat=chat, user=user)
    await fsm_ctx.set_state(state)
    await fsm_ctx.update_data(event_key=event_key, retries=0, clarifies=0)

async def _start_status_fsm(chat_id: int):
    chat = Chat(id=chat_id, type="private")
    user = User(id=chat_id, is_bot=False)
    fsm_ctx = FSMContext(storage=dispatcher.storage, chat=chat, user=user)
    await fsm_ctx.set_state(StatusFlow.waiting_status)
    await fsm_ctx.update_data(messages=[])
