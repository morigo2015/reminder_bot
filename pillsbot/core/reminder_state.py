# pillsbot/core/reminder_state.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Tuple, Iterable
from zoneinfo import ZoneInfo


class Status(str, Enum):
    PENDING = "pending"
    AWAITING = "awaiting"
    CONFIRMED = "confirmed"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class DoseKey:
    """Stable identity for a single scheduled dose."""

    patient_id: int
    date_str: str  # YYYY-MM-DD (engine-local date string)
    time_str: str  # HH:MM


@dataclass
class DoseInstance:
    """Mutable runtime state for a scheduled dose occurrence."""

    dose_key: DoseKey
    patient_id: int
    patient_label: str
    group_id: int
    nurse_user_id: int
    pill_text: str
    scheduled_dt_local: datetime
    status: str = Status.PENDING.value
    attempts_sent: int = 0
    preconfirmed: bool = False
    retry_task: Optional[asyncio.Task] = None
    last_message_ids: list[int] = field(default_factory=list)  # debug/trace only


class Clock:
    """Injectable, testable clock bound to a timezone."""

    def __init__(self, tz: ZoneInfo):
        self.tz = tz

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def today_str(self) -> str:
        return self.now().strftime("%Y-%m-%d")


class ReminderState:
    """
    Owns the in-memory state and selection logic.
    Only manipulates DoseInstance objects; orchestration lives in the engine.
    """

    def __init__(self, tz: ZoneInfo, clock: Clock):
        self.tz = tz
        self.clock = clock
        self._state: Dict[DoseKey, DoseInstance] = {}

    # -- dict-like read access for compatibility with existing tests --
    def get(self, key: DoseKey) -> Optional[DoseInstance]:
        return self._state.get(key)

    def values(self) -> Iterable[DoseInstance]:
        return self._state.values()

    def keys(self) -> Iterable[DoseKey]:
        return self._state.keys()

    @property
    def mapping(self) -> Dict[DoseKey, DoseInstance]:
        """Expose the raw mapping for compat with tests (read/write by engine only)."""
        return self._state

    # -- lifecycle ------------------------------------------------------
    def ensure_today_instances(self, patient: dict) -> None:
        """Create DoseInstance entries for today's date if missing."""
        today = self.clock.today_str()
        pid = patient["patient_id"]
        group_id = patient["group_id"]
        nurse_user_id = patient["nurse_user_id"]
        label = patient["patient_label"]

        for d in patient["doses"]:
            t_str: str = d["time"]
            pill_text: str = d["text"]
            key = DoseKey(pid, today, t_str)
            if key in self._state:
                continue
            dt_local = self._combine(today, t_str)
            self._state[key] = DoseInstance(
                dose_key=key,
                patient_id=pid,
                patient_label=label,
                group_id=group_id,
                nurse_user_id=nurse_user_id,
                pill_text=pill_text,
                scheduled_dt_local=dt_local,
            )

    # -- status helpers -------------------------------------------------
    def set_status(self, inst: DoseInstance, status: Status) -> None:
        inst.status = status.value

    def status(self, inst: DoseInstance) -> Status:
        return Status(inst.status)

    # -- selection logic ------------------------------------------------
    def select_target_for_confirmation(
        self, now_local: datetime, patient: dict
    ) -> Optional[DoseInstance]:
        """
        Prefer actively waiting; else the nearest upcoming (same day),
        excluding already confirmed/escalated.
        """
        pid = patient["patient_id"]
        today = self.clock.today_str()

        # 1) Actively waiting
        for d in patient["doses"]:
            key = DoseKey(pid, today, d["time"])
            inst = self._state.get(key)
            if inst and self.status(inst) == Status.AWAITING:
                return inst

        # 2) Nearest upcoming today (not confirmed/escalated)
        best: Tuple[Optional[DoseInstance], Optional[datetime]] = (None, None)
        for d in patient["doses"]:
            key = DoseKey(pid, today, d["time"])
            inst = self._state.get(key)
            if not inst or self.status(inst) in (Status.CONFIRMED, Status.ESCALATED):
                continue
            dt = inst.scheduled_dt_local
            if dt >= now_local and (best[1] is None or dt < best[1]):
                best = (inst, dt)

        return best[0]

    # -- utilities ------------------------------------------------------
    def _combine(self, yyyy_mm_dd: str, hh_mm: str) -> datetime:
        y, m, d = (int(x) for x in yyyy_mm_dd.split("-"))
        # Handle special case where time is "*" (any time)
        if hh_mm == "*":
            hh, mm = 12, 0  # Default to noon for "any time" doses
        else:
            hh, mm = (int(x) for x in hh_mm.split(":"))
        return datetime(y, m, d, hh, mm, tzinfo=self.tz)
