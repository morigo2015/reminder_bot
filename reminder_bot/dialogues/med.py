import re
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from services.scheduler import schedule_once, schedule_daily, cancel_jobs, dispatcher, _start_fsm
from services.config import config
from services.logging import CSVLogger
from services.escalation import escalate_to_nurse
from states import ReminderStates

router = Router()
reminder_logger = CSVLogger("reminder")

@router.message(Command("schedule"), F.args)
async def schedule_event_handler(message: Message):
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("Usage: /schedule <event_key> <HH:MM>")
        return
    event_key, time_str = args
    events = config.get("events", {})
    if event_key not in events:
        await message.reply(f"Unknown event key: {event_key}")
        return
    try:
        hh, mm = map(int, time_str.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except:
        await message.reply("Time format must be HH:MM")
        return
    schedule_daily(message.chat.id, event_key, time_str, reminder_main_handler, {"event_key": event_key})
    await message.reply(f"Scheduled daily reminder for '{event_key}' at {time_str}")

async def reminder_main_handler(job):
    data = job.data
    chat_id = data["chat_id"]
    event_key = data["event_key"]
    bot = job.bot
    event = config["events"][event_key]
    cancel_jobs(chat_id, event_key)
    await bot.send_message(chat_id, event["main"])
    # Start FSM with correct initial state
    await _start_fsm(chat_id, event_key, ReminderStates.waiting_confirmation)
    await reminder_logger.log(chat_id, event_key=event_key, action="sent_main")
    # Schedule retry
    schedule_once(chat_id, f"{event_key}:retry", event["retry_delay"], reminder_retry_handler, {"event_key": event_key})

async def reminder_retry_handler(job):
    data = job.data
    chat_id = data["chat_id"]
    event_key = data["event_key"]
    bot = job.bot
    event = config["events"][event_key]
    from aiogram.types import Chat, User
    from aiogram.fsm.context import FSMContext
    dp = dispatcher
    chat = Chat(id=chat_id, type="private")
    user = User(id=chat_id, is_bot=False)
    fsm_ctx = FSMContext(storage=dp.storage, chat=chat, user=user)
    state_data = await fsm_ctx.get_data()
    retries = state_data.get("retries", 0)
    if retries < event["retries"]:
        await bot.send_message(chat_id, event["retry"])
        retries += 1
        await fsm_ctx.update_data(retries=retries)
        await reminder_logger.log(chat_id, event_key=event_key, action=f"retry_{retries}")
        schedule_once(chat_id, f"{event_key}:retry", event["retry_delay"], reminder_retry_handler, {"event_key": event_key})
    else:
        schedule_once(chat_id, f"{event_key}:clarify", config["timings"]["clarify_delay"], reminder_clarify_handler, {"event_key": event_key})

async def reminder_clarify_handler(job):
    data = job.data
    chat_id = data["chat_id"]
    event_key = data["event_key"]
    bot = job.bot
    event = config["events"][event_key]
    from aiogram.types import Chat, User
    from aiogram.fsm.context import FSMContext
    dp = dispatcher
    chat = Chat(id=chat_id, type="private")
    user = User(id=chat_id, is_bot=False)
    fsm_ctx = FSMContext(storage=dp.storage, chat=chat, user=user)
    state_data = await fsm_ctx.get_data()
    clarifies = state_data.get("clarifies", 0)
    if clarifies < event["clarify_retries"]:
        await bot.send_message(chat_id, event.get("retry"))
        clarifies += 1
        await fsm_ctx.update_data(clarifies=clarifies)
        await reminder_logger.log(chat_id, event_key=event_key, action=f"clarify_{clarifies}")
        schedule_once(chat_id, f"{event_key}:clarify", config["timings"]["clarify_delay"], reminder_clarify_handler, {"event_key": event_key})
    else:
        await escalate_to_nurse(chat_id, event_key, bot)
        await reminder_logger.log(chat_id, event_key=event_key, action="escalated")
        # Clear FSM
        from aiogram.fsm.context import FSMContext
        from aiogram.types import Chat, User
        fsm_ctx = FSMContext(storage=dispatcher.storage, chat=Chat(id=chat_id, type="private"), user=User(id=chat_id, is_bot=False))
        await fsm_ctx.clear()

from aiogram import F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

@router.message(ReminderStates.waiting_confirmation, F.text.regexp(config["patterns"]["confirm_ok"]))
@router.message(ReminderStates.waiting_clarification, F.text.regexp(config["patterns"]["confirm_ok"]))
async def confirm_success(message: Message, state: FSMContext):
    data = await state.get_data()
    event_key = data.get("event_key")
    chat_id = message.chat.id
    cancel_jobs(chat_id, event_key)
    await message.reply("Дякую, підтверджено.")
    await reminder_logger.log(chat_id, event_key=event_key, action="confirmed")
    await state.clear()
