from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Dict

@dataclass(frozen=True)
class Event:
    """Immutable definition of reminder scheduling logic."""
    event_name: str
    chat_id: int
    scheduler_args: dict      # kwargs passed directly to APScheduler.add_job
    main_text: str
    retry_text: str
    retry_delay_seconds: int
    retries: int = 0
    escalate: bool = True

@dataclass
class RuntimeState:
    """In‑memory tracking of confirmation & clarification attempts."""
    attempt: int = 0                # number of retry attempts already sent
    clarify_attempt: int = 0        # number of clarification messages sent
    confirmed: bool = False
    retry_job_id: Optional[str] = None
    clarify_job_id: Optional[str] = None

@dataclass
class PressureDayState:
    """Track if today's pressure reading has been received."""
    received: bool = False
    day: date = field(default_factory=date.today)

    def reset_if_new_day(self) -> None:
        today = date.today()
        if today != self.day:
            self.day = today
            self.received = False