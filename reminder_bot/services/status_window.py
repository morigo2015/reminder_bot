"""Manage per‑chat health status collection windows."""
from __future__ import annotations
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Deque, Dict, List

from ..utils.time import kyiv_now
from ..utils import logging as log

class StatusWindowManager:
    """Tracks open status windows and stored messages."""

    def __init__(self, window_sec: int, msg_limit: int):
        self.window_sec = window_sec
        self.msg_limit = msg_limit
        # chat_id -> (window_end, deque[str])
        self._windows: Dict[int, tuple[datetime, Deque[str]]] = {}

    def add_message(self, chat_id: int, text: str) -> None:
        now = kyiv_now()
        window_end, msgs = self._windows.get(chat_id, (now, deque()))
        if now >= window_end:
            # start new window
            window_end = now + timedelta(seconds=self.window_sec)
            msgs = deque()
        # store message or mark dropped
        if len(msgs) < self.msg_limit:
            msgs.append(text)
            log.log_status(text, dropped=False)
        else:
            log.log_status(text, dropped=True)
        self._windows[chat_id] = (window_end, msgs)