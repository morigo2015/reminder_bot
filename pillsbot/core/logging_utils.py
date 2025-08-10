# pillsbot/core/logging_utils.py
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(cfg: Any) -> logging.Logger:
    """
    Configure logging:
    - Console shows INFO and above (clean runtime output).
    - Audit log file stores DEBUG and above (full trace).
    """
    log_dir = os.path.dirname(cfg.AUDIT_LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger("pillsbot")
    root.setLevel(logging.DEBUG)  # Allow DEBUG to propagate to file handler

    fmt = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # File handler — DEBUG level, full history
    fh = RotatingFileHandler(
        cfg.AUDIT_LOG_FILE, maxBytes=1_000_000, backupCount=10, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)

    # Console handler — INFO level, clean output
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)

    root.handlers.clear()
    root.addHandler(fh)
    root.addHandler(ch)

    return root


def kv(**kwargs: Any) -> str:
    """Key=value compact formatting (values repr()'d for clarity)."""
    return " ".join(f"{k}={v!r}" for k, v in kwargs.items())
