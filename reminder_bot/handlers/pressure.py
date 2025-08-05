"""Handler for blood‑pressure readings."""
from __future__ import annotations
import re
from aiogram import Router
from aiogram.types import Message

from reminder_bot.config.dialogs_loader import DIALOGS
from reminder_bot.utils import logging as log
from reminder_bot.models import PressureDayState

router = Router()
_PREFIX_PATTERNS = DIALOGS['patterns'].get('pressure_prefix', [])
_TRIPLE_INT = re.compile(r"(\d{2,3})[\s,]+(\d{2,3})[\s,]+(\d{2,3})")

# per‑chat day state
_PRESSURE_STATE: dict[int, PressureDayState] = {}

def _text_starts_with_prefix(text: str) -> bool:
    return any(p.match(text) for p in _PREFIX_PATTERNS)

@router.message()
async def handle_pressure(message: Message):
    text = (message.text or "").strip()
    if not text:
        return
    # if prefix required, ensure presence or search inside
    if _text_starts_with_prefix(text):
        # remove the prefix part
        text = _TRIPLE_INT.search(text)
    match = _TRIPLE_INT.search(text)
    if not match:
        return  # ignore
    high, low, hbr = map(int, match.groups())
    log.log_pressure(high, low, hbr)

    st = _PRESSURE_STATE.setdefault(message.chat.id, PressureDayState())
    st.received = True