# app/ctx.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler


@dataclass
class AppCtx:
    bot: Bot
    scheduler: AsyncIOScheduler


_CTX: Optional[AppCtx] = None


def set_ctx(ctx: AppCtx) -> None:
    global _CTX
    _CTX = ctx


def get_ctx() -> AppCtx:
    if _CTX is None:
        raise RuntimeError("App context is not initialized")
    return _CTX
