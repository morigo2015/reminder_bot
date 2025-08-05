"""Handler for free‑form health status messages."""
from __future__ import annotations
import re
from aiogram import Router
from aiogram.types import Message

from reminder_bot.config.dialogs_loader import DIALOGS
from reminder_bot.services.status_window import StatusWindowManager

_PATTERNS = DIALOGS['patterns'].get('health_prefix', [])
_TIMINGS = DIALOGS['timings']

router = Router()
_mgr = StatusWindowManager(
    window_sec=_TIMINGS['status_window_sec'],
    msg_limit=_TIMINGS['log_status_max_msgs'],
)

def _match_prefix(text: str) -> bool:
    return any(p.match(text) for p in _PATTERNS)

@router.message()
async def handle_status(message: Message):
    text = (message.text or "").strip()
    if not _match_prefix(text):
        return
    _mgr.add_message(message.chat.id, text[: _TIMINGS['log_msg_max']])