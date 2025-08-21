# app/main.py
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Optional

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

# Global bot for internal job handlers (lazy import workaround)
BOT: Optional[Bot] = None


async def _setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.TZ)
    await schedule_daily_jobs(scheduler)
    scheduler.start()
    # attach for job handlers
    bot["scheduler"] = scheduler
    return scheduler


async def start() -> None:
    config.fail_fast_config()
    global BOT
    BOT = Bot(token=config.BOT_TOKEN, parse_mode=None)
    dp = Dispatcher()

    # ---- Commands ----
    @dp.message(Command("status"))
    async def cmd_status(msg: Message):
        now = format_kyiv(now_local())
        await msg.reply(f"OK {now} (Kyiv). Jobs active ✅")

    # ---- Group moderation & routing ----
    @dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
    async def on_group_message(msg: Message):
        # Route only known patient messages; warn others
        pid = _find_patient_by_group(msg.chat.id)
        if pid is None:
            return  # unknown group, ignore
        if msg.from_user is None:
            return
        if msg.from_user.is_bot:
            return
        # Only patient should speak in the group (bot <-> patient). Others get a gentle warning.
        if not _is_patient_user(pid, msg.from_user.id):
            await msg.reply(only_patient_can_write())
            return
        await handle_patient_text(
            BOT,
            BOT["scheduler"],
            patient_id=pid,
            text=msg.text or "",
            chat_id=msg.chat.id,
            tg_message_id=msg.message_id,
        )

    # Fallback: any private messages (if used during PoC) → ack and ignore
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

    # ready
    scheduler = await _setup_scheduler(BOT)
    try:
        await dp.start_polling(BOT, handle_signals=False)
    finally:
        with suppress(Exception):
            scheduler.shutdown(wait=False)
        await BOT.session.close()


def _find_patient_by_group(group_chat_id: int) -> Optional[int]:
    for pid, cfg in config.PATIENTS.items():
        if cfg.get("group_chat_id") == group_chat_id:
            return pid
    return None


def _is_patient_user(patient_id: int, user_id: int) -> bool:
    # MVP: any human in the group can type as "patient".
    # If you want strict identity checks, store Telegram user_id per patient in config and validate here.
    return True


if __name__ == "__main__":
    asyncio.run(start())
