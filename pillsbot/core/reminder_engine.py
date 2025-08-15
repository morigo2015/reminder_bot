# pillsbot/core/reminder_engine.py
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Dict, Set
from zoneinfo import ZoneInfo

from pillsbot.core.matcher import Matcher
from pillsbot.core.i18n import fmt
from pillsbot.core.logging_utils import kv
from pillsbot.core.measurements import MeasurementRegistry
from pillsbot.core.reminder_state import (
    Clock,
    Status,
    DoseKey,
    DoseInstance,
    ReminderState,
)
from pillsbot.core.reminder_messaging import ReminderMessenger
from pillsbot.core.reminder_retry import RetryManager


# -------------------------------------------------------------------------------------------------
# Public inbound message type (kept here for backwards-compat imports in tests)
# -------------------------------------------------------------------------------------------------
@dataclass
class IncomingMessage:
    group_id: int
    sender_user_id: int
    text: str
    sent_at_utc: datetime


class ReminderEngine:
    """
    v4: Single dynamic inline menu (delete old → post new). The engine ensures that
    after every visible event the last message is the menu.
    """

    def __init__(self, config: Any, adapter: Any | None, clock: Optional[Clock] = None):
        self.cfg = config
        self.adapter = adapter
        tz = getattr(config, "TZ", None) or ZoneInfo(
            getattr(config, "TIMEZONE", "Europe/Kyiv")
        )
        self.clock = clock or Clock(tz)

        # Core services
        self.matcher = Matcher(getattr(config, "CONFIRM_PATTERNS", []))
        self.measures = MeasurementRegistry(tz, getattr(config, "MEASURES", None))
        self.log = logging.getLogger("pillsbot.engine")

        # State & messaging
        self.state_mgr = ReminderState(tz, self.clock)
        self.messenger = ReminderMessenger(adapter=self.adapter, log=self.log)
        self._escalated: Set[DoseKey] = set()

        self.patient_index: Dict[int, dict] = {}
        self.group_to_patient: Dict[int, int] = {}

        self.retry_mgr: Optional[RetryManager] = None

    def attach_adapter(self, adapter: Any) -> None:
        self.adapter = adapter
        self.messenger.adapter = adapter
        self.log.debug("engine.adapter.attached " + kv(kind=type(adapter).__name__))

    async def start(self, scheduler: Any | None) -> None:
        # Build indices
        for p in getattr(self.cfg, "PATIENTS", []):
            pid = p["patient_id"]
            self.patient_index[pid] = p
            self.group_to_patient[p["group_id"]] = pid
            self.state_mgr.ensure_today_instances(p)

        # Wire retry
        self.retry_mgr = RetryManager(
            interval_seconds=int(getattr(self.cfg, "RETRY_INTERVAL_S", 30)),
            max_attempts=int(getattr(self.cfg, "MAX_RETRY_ATTEMPTS", 3)),
            send_repeat=self._send_repeat_wrapper,
            on_escalate=self._on_escalate_wrapper,
            set_status=self.state_mgr.set_status,
            get_status=self.state_mgr.status,
            logger=self.log,
        )

        # Optional scheduler passthrough kept for compatibility
        if scheduler is not None:
            try:
                for p in getattr(self.cfg, "PATIENTS", []):
                    for d in p["doses"]:
                        scheduler.add_job(
                            self._start_dose_job,
                            kwargs={
                                "patient_id": p["patient_id"],
                                "time_str": d["time"],
                            },
                        )
                    for chk in p.get("measurement_checks", []):
                        scheduler.add_job(
                            self._job_measure_check,
                            kwargs={
                                "patient_id": p["patient_id"],
                                "measure_id": chk["measure_id"],
                            },
                        )
            except Exception:
                pass

    # ---- incoming from adapter --------------------------------------------------------
    async def on_patient_message(self, msg: IncomingMessage) -> None:
        self.log.info(
            "msg.engine.in "
            + kv(
                group_id=msg.group_id,
                sender_user_id=msg.sender_user_id,
                text=(msg.text or ""),
            )
        )

        pid = self.group_to_patient.get(msg.group_id)
        if pid is None or pid != msg.sender_user_id:
            self.log.debug(
                "msg.engine.reject "
                + kv(
                    reason="patient-only",
                    group_id=msg.group_id,
                    sender_user_id=msg.sender_user_id,
                )
            )
            return

        patient = self.patient_index[pid]
        text = (msg.text or "").strip()

        # Measurements
        mm = self.measures.match(text)
        if mm:
            mid, body = mm
            parsed = self.measures.parse(mid, body)
            if parsed.get("ok"):
                now_local = self.clock.now()
                self.measures.append_csv(
                    mid, now_local, pid, patient["patient_label"], parsed["values"]
                )
                if mid == "pressure":
                    sys_v, dia_v = parsed["values"]
                    await self._reply(
                        patient["group_id"],
                        "ack_pressure",
                        systolic=sys_v,
                        diastolic=dia_v,
                    )
                elif mid == "weight":
                    (w,) = parsed["values"]
                    await self._reply(patient["group_id"], "ack_weight", kg=w)
                else:
                    await self._reply(patient["group_id"], "unknown_text")
            else:
                if mid == "pressure":
                    await self._reply(patient["group_id"], "err_pressure")
                elif mid == "weight":
                    await self._reply(patient["group_id"], "err_weight")
                else:
                    await self._reply(patient["group_id"], "unknown_text")

            # After measurement handling, refresh menu
            await self.show_current_menu(patient["group_id"])
            return

        # Confirmation via text
        if self.matcher.matches_confirmation(text.lower().strip()):
            await self._handle_confirmation_text(patient)
            return

        # Help keyword
        if text.lower() in {"help", "?", "довідка"}:
            await self._reply(patient["group_id"], "help_text")
            await self.show_current_menu(patient["group_id"])
            return

        # Fallback
        await self._reply(patient["group_id"], "unknown_text")
        await self.show_current_menu(patient["group_id"])

    # ---- menus / actions --------------------------------------------------------------
    async def show_current_menu(self, group_id: int) -> None:
        """
        Post exactly one menu at the bottom:
        - If a dose is actively AWAITING → show reminder text + menu with Confirm.
        - Otherwise → show idle text + menu without Confirm.
        """
        pid = self.group_to_patient.get(group_id)
        if pid is None:
            return
        patient = self.patient_index.get(pid)
        if not patient:
            return

        target = self.state_mgr.select_target_for_confirmation(
            self.clock.now(), patient
        )

        if target and self.state_mgr.status(target) == Status.AWAITING:
            await self.messenger.send_reminder_step(target)
            return

        await self.messenger.send_home_step(group_id, pid, can_confirm=False)

    async def quick_confirm(self, group_id: int, from_user_id: int) -> None:
        """Handle '✅ TAKE' tap; patient-only is enforced upstream in adapter."""
        pid = self.group_to_patient.get(group_id)
        if pid is None or pid != from_user_id:
            return
        patient = self.patient_index.get(pid)
        if not patient:
            return
        await self._handle_confirmation_text(patient)

    # ---- jobs / orchestration ----------------------------------------------------------
    async def _start_dose_job(self, *, patient_id: int, time_str: str) -> None:
        patient = self.patient_index.get(patient_id)
        if not patient:
            self.log.debug(
                "job.trigger.miss "
                + kv(reason="unknown patient", patient_id=patient_id)
            )
            return

        key = DoseKey(patient_id, self.clock.today_str(), time_str)
        inst = self.state_mgr.get(key)
        if inst is None:
            self.state_mgr.ensure_today_instances(patient)
            inst = self.state_mgr.get(key)
            if inst is None:
                self.log.error(
                    "job.trigger.miss "
                    + kv(
                        patient_id=patient_id, time=time_str, reason="state not created"
                    )
                )
                return

        if self.state_mgr.status(inst) == Status.CONFIRMED:
            self.log.debug(
                "job.trigger.skip "
                + kv(patient_id=patient_id, time=time_str, reason="confirmed")
            )
            return

        self.state_mgr.set_status(inst, Status.AWAITING)
        inst.attempts_sent = 1

        await self.messenger.send_reminder_step(inst)
        await self._start_retry(inst)

    async def _job_measure_check(self, *, patient_id: int, measure_id: str) -> None:
        patient = self.patient_index.get(patient_id)
        if not patient:
            return
        today = self.clock.now().date()
        if not self.measures.has_today(measure_id, patient_id, today):
            await self._reply(
                patient["group_id"],
                "escalate_group"
                if measure_id not in {"pressure", "weight"}
                else "unknown_text",
            )
            # Immediately refresh menu after any bot-visible event
            await self.show_current_menu(patient["group_id"])

    # ---- retry glue -------------------------------------------------------------------
    async def _start_retry(self, inst: DoseInstance) -> None:
        if self.retry_mgr is None:
            return
        await self._stop_retry(inst)
        inst.retry_task = asyncio.create_task(self.retry_mgr.run(inst))

    async def _stop_retry(self, inst: DoseInstance) -> None:
        t = inst.retry_task
        if t and not t.done():
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        inst.retry_task = None

    async def _send_repeat_wrapper(self, inst: DoseInstance) -> None:
        # v4: final pre-send status check — if not AWAITING, do not send the retry.
        if self.state_mgr.status(inst) != Status.AWAITING:
            return
        await self.messenger.send_reminder_step(inst)

    async def _on_escalate_wrapper(self, inst: DoseInstance) -> None:
        # Send escalation messages
        await self.messenger.send_escalation(inst)
        self._escalated.add(inst.dose_key)
        self._log_outcome_csv(inst, "escalated")
        # NEW: keep the invariant "menu is last" after escalation.
        await self.show_current_menu(inst.group_id)

    # ---- confirmation handling ---------------------------------------------------------
    async def _handle_confirmation_text(self, patient: dict) -> None:
        now = self.clock.now()
        target = self.state_mgr.select_target_for_confirmation(now, patient)
        if not target:
            # Not awaiting → neutral line + refresh menu
            await self._reply(patient["group_id"], "unknown_text")
            await self.show_current_menu(patient["group_id"])
            return

        # Idempotent confirm
        if self.state_mgr.status(target) == Status.CONFIRMED:
            await self._reply(patient["group_id"], "ack_confirm")
            await self.show_current_menu(patient["group_id"])
            return

        self.state_mgr.set_status(target, Status.CONFIRMED)
        await self._stop_retry(target)
        self.log.info(
            "dose.confirm "
            + kv(
                patient_id=target.patient_id,
                time=target.dose_key.time_str,
                source="tap/text",
            )
        )

        if target.dose_key in self._escalated:
            await self.messenger.send_nurse_notice(
                target.nurse_user_id,
                fmt(
                    "nurse_late_confirm_dm",
                    patient_label=target.patient_label,
                    date=target.dose_key.date_str,
                    time=target.dose_key.time_str,
                    pill_text=target.pill_text,
                ),
            )
            self._escalated.discard(target.dose_key)

        self._log_outcome_csv(target, "confirmed")

        # Ack + refresh menu without confirm
        await self._reply(patient["group_id"], "ack_confirm")
        await self.show_current_menu(patient["group_id"])

    # ---- plain replies ---------------------------------------------------------------
    async def _reply(
        self, group_id: int, template_key: str, **fmt_args: Any
    ) -> Optional[int]:
        """Send a plain group message using i18n template (menu is managed by callers)."""
        return await self.messenger.send_group_template(
            group_id, template_key, **fmt_args
        )

    # ---- misc -------------------------------------------------------------------------
    def _log_outcome_csv(self, inst: DoseInstance, status: str) -> None:
        line = (
            f"{inst.scheduled_dt_local.strftime('%Y-%m-%d %H:%M')}, "
            f"{inst.patient_id}, {inst.patient_label}, {inst.pill_text}, {status}, {inst.attempts_sent}\n"
        )
        path = getattr(self.cfg, "LOG_FILE", "pillsbot/logs/pills.csv")
        import os

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    @property
    def state(self):
        return self.state_mgr.mapping
