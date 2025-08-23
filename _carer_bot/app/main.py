# app/main.py
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import config
from .csvlog import csv_append
from .events import SC_OTHER, EV_ACK
from .policies import handle_patient_text, schedule_daily_jobs
from .prompts import only_patient_can_write
from .utils import format_kyiv, now_local
from .ctx import AppCtx, set_ctx, get_ctx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate-limit moderation warnings: group_id -> last_sent_at
_LAST_WARN_AT: Dict[int, datetime] = {}


def _should_warn_group(group_id: int) -> bool:
    last = _LAST_WARN_AT.get(group_id)
    if not last:
        return True
    return now_local() - last >= timedelta(minutes=10)


def _mark_warned(group_id: int) -> None:
    _LAST_WARN_AT[group_id] = now_local()


async def _setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.TZ)
    await schedule_daily_jobs(scheduler, bot)
    scheduler.start()
    return scheduler


async def start() -> None:
    config.fail_fast_config()
    bot = Bot(token=config.BOT_TOKEN)  # no parse_mode tweaks
    dp = Dispatcher()
    scheduler = await _setup_scheduler(bot)
    set_ctx(AppCtx(bot=bot, scheduler=scheduler))

    # ---- Commands ----
    @dp.message(Command("status"))
    async def cmd_status(msg: Message):
        now = format_kyiv(now_local())
        await msg.reply(f"OK {now} (Kyiv). Jobs active ✅")

    @dp.message(Command("echo"))
    async def cmd_echo(msg: Message):
        # Handy for grabbing the real chat_id to paste into config.PATIENTS / CAREGIVER_CHAT_ID
        await msg.reply(f"chat_id: {msg.chat.id}")

    # ---- Group moderation & routing ----
    @dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
    async def on_group_message(msg: Message):
        pid = _find_patient_by_group(msg.chat.id)
        if pid is None or msg.from_user is None or msg.from_user.is_bot:
            return
        # Optional strict check if patient_user_id is configured
        expected_uid = config.PATIENTS[pid].get("patient_user_id")
        if expected_uid is not None and msg.from_user.id != expected_uid:
            if _should_warn_group(msg.chat.id):
                await msg.reply(only_patient_can_write())
                _mark_warned(msg.chat.id)
            return
        await handle_patient_text(
            bot,
            get_ctx().scheduler,
            patient_id=pid,
            text=msg.text or "",
            chat_id=msg.chat.id,
            tg_message_id=msg.message_id,
        )

    # Fallback: any private messages → ack and ignore
    @dp.message(F.chat.type == ChatType.PRIVATE)
    async def on_private(msg: Message):
        csv_append(
            scenario=SC_OTHER,
            event=EV_ACK,
            patient_id=-1,
            group_chat_id=msg.chat.id,
            text=msg.text or "",
        )
        await msg.reply("Цей бот працює лише в приватній групі пацієнта.")

    try:
        await dp.start_polling(bot, handle_signals=False)
    finally:
        with suppress(Exception):
            scheduler.shutdown(wait=False)
        await bot.session.close()


def _find_patient_by_group(group_chat_id: int) -> Optional[int]:
    for pid, p in config.PATIENTS.items():
        if p.get("group_chat_id") == group_chat_id:
            return pid
    return None


if __name__ == "__main__":
    asyncio.run(start())
