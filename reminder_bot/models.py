from dataclasses import dataclass

@dataclass(frozen=True)
class Event:
    """Immutable definition of reminder scheduling logic."""
    event_name: str
    chat_id: int
    scheduler_args: dict      # kwargs passed directly to APScheduler.add_job
    main_message: str
    retry_message: str
    retries: int
    retry_delay_seconds: int
    escalate: bool = True

@dataclass
class RuntimeState:
    """In‑memory tracking state for retries and confirmation."""
    attempt: int = 0
    confirmed: bool = False
    retry_job_id: str | None = None
