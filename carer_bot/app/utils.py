# app/utils.py
from __future__ import annotations
from datetime import datetime
from . import config


def dbg(msg: str) -> None:
    """
    Lightweight debug printer for PoC.
    Prints only when config.DEBUG_MODE is True.
    """
    if not config.DEBUG_MODE:
        return
    ts = datetime.now(config.TZ).strftime("%H:%M:%S")
    print(f"[DEBUG {ts}] {msg}", flush=True)
