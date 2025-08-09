from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, Any, List
from zoneinfo import ZoneInfo
import os

from .matcher import Matcher
from .i18n import fmt

@dataclass(frozen=True)
class DoseKey:
    patient_id: int
    date_str: str   # YYYY-MM-DD
    time_str: str   # HH:MM

@dataclass
class DoseInstance:
    dose_key: DoseKey
    patient_id: int
    patient_label: str
    group_id: int
    nurse_user_id: int
    pill_text: str
    scheduled_dt_local: datetime
    status: str = "Pending"  # Pending | AwaitingConfirmation | Confirmed | Escalated
    attempts_sent: int = 0
    preconfirmed: bool = False
    retry_task: Optional[asyncio.Task] = None

@dataclass
class IncomingMessage:
    group_id: int
    sender_user_id: int
    text: str
    sent_at_utc: datetime

class ReminderEngine:
    def __init__(self, config: Any, adapter: Any):
        self.cfg = config
        self.adapter = adapter
        self.tz: ZoneInfo = config.TZ
        self.matcher = Matcher(config.CONFIRM_PATTERNS)
        self.state: Dict[DoseKey, DoseInstance] = {}
        self.group_to_patient: Dict[int, int] = {p["group_id"]: p["patient_id"] for p in config.PATIENTS}
        self.patient_index: Dict[int, dict] = {p["patient_id"]: p for p in config.PATIENTS}
        os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

    # --- Logging ---
    def _log(self, when_local: datetime, patient_id: int, patient_label: str, pill_text: str, status: str, attempts: int) -> None:
        line = f"{when_local.strftime('%Y-%m-%d %H:%M')}, {patient_id}, {patient_label}, {pill_text}, {status}, {attempts}\n"
        with open(self.cfg.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)

    # --- Helpers ---
    def _today_str(self) -> str:
        return datetime.now(self.tz).strftime("%Y-%m-%d")

    def _local_now(self) -> datetime:
        return datetime.now(self.tz)

    def _get_dosekey(self, patient_id: int, date_str: str, time_str: str) -> DoseKey:
        return DoseKey(patient_id, date_str, time_str)

    def _ensure_today_instances(self) -> None:
        today = self._today_str()
        for p in self.cfg.PATIENTS:
            for d in p["doses"]:
                key = self._get_dosekey(p["patient_id"], today, d["time"])
                if key not in self.state:
                    hh, mm = map(int, d["time"].split(":"))
                    sched = datetime.now(self.tz).replace(hour=hh, minute=mm, second=0, microsecond=0)
                    inst = DoseInstance(
                        dose_key=key,
                        patient_id=p["patient_id"],
                        patient_label=p["patient_label"],
                        group_id=p["group_id"],
                        nurse_user_id=p["nurse_user_id"],
                        pill_text=d["text"],
                        scheduled_dt_local=sched,
                    )
                    self.state[key] = inst

    async def start(self, scheduler) -> None:
        """Prepare state and install daily jobs into the APScheduler."""
        self._ensure_today_instances()

        # Install daily cron jobs for each dose
        for p in self.cfg.PATIENTS:
            for d in p["doses"]:
                hh, mm = map(int, d["time"].split(":"))
                scheduler.add_job(
                    self._start_dose_job,
                    trigger="cron",
                    hour=hh,
                    minute=mm,
                    timezone=self.tz,
                    args=[p["patient_id"], d["time"]],
                    id=f"dose_{p['patient_id']}_{d['time']}",
                    replace_existing=True,
                )

    async def _start_dose_job(self, patient_id: int, time_str: str) -> None:
        """Called by scheduler at dose time in Europe/Kyiv."""
        self._ensure_today_instances()
        key = self._get_dosekey(patient_id, self._today_str(), time_str)
        inst = self.state.get(key)
        if not inst:
            return
        if inst.status == "Confirmed":
            return  # preconfirmed earlier

        # Send first reminder
        await self.adapter.send_group_message(inst.group_id, fmt("reminder", pill_text=inst.pill_text))
        inst.status = "AwaitingConfirmation"
        inst.attempts_sent = 1

        # Start retry loop
        inst.retry_task = asyncio.create_task(self._retry_loop(inst))

    async def _retry_loop(self, inst: DoseInstance) -> None:
        I = self.cfg.RETRY_INTERVAL_S
        N = self.cfg.MAX_RETRY_ATTEMPTS
        # We already sent attempt #1 in _start_dose_job
        while inst.status == "AwaitingConfirmation":
            # Wait before deciding next action
            await asyncio.sleep(I)
            if inst.status != "AwaitingConfirmation":
                break
            if inst.attempts_sent < N:
                await self.adapter.send_group_message(inst.group_id, fmt("repeat_reminder"))
                inst.attempts_sent += 1
            else:
                # escalate
                await self.adapter.send_group_message(inst.group_id, fmt("escalate_group"))
                when = inst.scheduled_dt_local
                date = when.strftime("%Y-%m-%d")
                time = when.strftime("%H:%M")
                await self.adapter.send_nurse_dm(inst.nurse_user_id,
                                                 fmt("escalate_dm", patient_label=inst.patient_label, date=date, time=time, pill_text=inst.pill_text))
                inst.status = "Escalated"
                self._log(inst.scheduled_dt_local, inst.patient_id, inst.patient_label, inst.pill_text, "Escalated", inst.attempts_sent)
                break

    # --- Incoming messages from adapter ---
    async def on_patient_message(self, msg: IncomingMessage) -> None:
        # Only accept messages from known groups and from the patient user ID for that group
        pid = self.group_to_patient.get(msg.group_id)
        if pid is None or pid != msg.sender_user_id:
            return

        text = msg.text or ""
        if not self.matcher.matches_confirmation(text):
            return

        now_local = self._local_now()
        today = self._today_str()

        # Determine the relevant upcoming dose for today for this patient (next chronological)
        patient = self.patient_index[pid]
        upcoming: Optional[DoseInstance] = None
        min_dt = None
        for d in patient["doses"]:
            key = self._get_dosekey(pid, today, d["time"])
            inst = self.state.get(key)
            if not inst:
                continue
            if inst.status in ("Confirmed", "Escalated"):
                continue
            dt = inst.scheduled_dt_local
            if dt >= now_local and (min_dt is None or dt < min_dt):
                upcoming = inst
                min_dt = dt

        # If awaiting confirmation now for any dose, prioritize that instance
        awaiting_now: Optional[DoseInstance] = None
        for d in patient["doses"]:
            key = self._get_dosekey(pid, today, d["time"])
            inst = self.state.get(key)
            if inst and inst.status == "AwaitingConfirmation":
                awaiting_now = inst
                break

        target = awaiting_now or upcoming

        if target is None:
            # Nothing to confirm now; too early
            await self.adapter.send_group_message(patient["group_id"], fmt("too_early"))
            return

        # If we have an awaiting instance → normal confirmation
        if target.status == "AwaitingConfirmation":
            target.status = "Confirmed"
            if target.retry_task and not target.retry_task.done():
                target.retry_task.cancel()
            self._log(target.scheduled_dt_local, target.patient_id, target.patient_label, target.pill_text, "OK", target.attempts_sent)
            await self.adapter.send_group_message(target.group_id, fmt("confirm_ack"))
            return

        # Else, we are before the first send for that dose; check grace
        delta = (target.scheduled_dt_local - now_local).total_seconds()
        if 0 <= delta <= self.cfg.TAKING_GRACE_INTERVAL_S:
            target.status = "Confirmed"
            target.preconfirmed = True
            target.attempts_sent = 0
            self._log(target.scheduled_dt_local, target.patient_id, target.patient_label, target.pill_text, "OK", 0)
            await self.adapter.send_group_message(target.group_id, fmt("preconfirm_ack"))
        else:
            await self.adapter.send_group_message(target.group_id, fmt("too_early"))
