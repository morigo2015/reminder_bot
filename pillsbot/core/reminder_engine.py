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
from pillsbot.core.i18n import fmt, MESSAGES
from pillsbot.core.logging_utils import kv
from pillsbot.core.measurements import MeasurementRegistry, parse_pressure_free, parse_weight_free
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

    Option A: tapping Тиск/Вага shows a short hint with the inline menu in ONE message.
    The very next patient message is interpreted according to that hint (lightweight,
    one-shot expectation per chat). No long-lived sessions.
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

        # One-shot expectation for next user message after a tap: {"pressure"|"weight"}
        self._expect_next: Dict[int, str] = {}  # keyed by group_id

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
        group_id = patient["group_id"]

        # --- A) Confirmation via text (CRITICAL INTENT) ---
        if self.matcher.matches_confirmation(text.lower().strip()):
            await self._handle_confirmation_text(patient)
            return

        # --- B) Help commands (should not be blocked by hint expectation) ---
        if text.lower() in {"help", "?", "довідка"}:
            await self.show_help(group_id)
            return

        # --- C) One-shot expectation set by a recent tap (pressure/weight) ---
        expect = self._expect_next.pop(group_id, None)
        if expect == "pressure":
            await self._handle_pressure_text(patient, text)
            await self.show_current_menu(group_id)
            return
        if expect == "weight":
            await self._handle_weight_text(patient, text)
            await self.show_current_menu(group_id)
            return

        # --- D) Typed keywords (start-anchored), then tolerant parse on the body ---
        mm = self.measures.match(text)
        if mm:
            mid, body = mm
            if mid == "pressure":
                await self._handle_pressure_text(patient, body)
                await self.show_current_menu(group_id)
                return
            if mid == "weight":
                await self._handle_weight_text(patient, body)
                await self.show_current_menu(group_id)
                return

        # --- E) Fallback ---
        await self._reply(group_id, "unknown_text")
        await self.show_current_menu(group_id)

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

        await self.messenger.send_home_step(group_id, can_confirm=False)

    async def show_hint_menu(self, group_id: int, *, kind: str) -> None:
        """
        Show the short hint (pressure/weight) with the inline menu in ONE message,
        and set a one-shot expectation for the very next patient message.
        """
        pid = self.group_to_patient.get(group_id)
        if pid is None:
            return
        patient = self.patient_index.get(pid)
        if not patient:
            return

        # Set expectation
        if kind in {"pressure", "weight"}:
            self._expect_next[group_id] = kind

        # Can we show confirm row?
        target = self.state_mgr.select_target_for_confirmation(self.clock.now(), patient)
        can_confirm = bool(target and self.state_mgr.status(target) == Status.AWAITING)

        # Which hint text?
        text = MESSAGES["prompt_pressure"] if kind == "pressure" else MESSAGES["prompt_weight"]

        await self.messenger.send_menu(group_id, text=text, can_confirm=can_confirm)

    async def quick_confirm(self, group_id: int, from_user_id: int) -> None:
        """Handle '✅ TAKE' tap; patient-only is enforced upstream in adapter."""
        pid = self.group_to_patient.get(group_id)
        if pid is None or pid != from_user_id:
            return
        patient = self.patient_index.get(pid)
        if not patient:
            return
        await self._handle_confirmation_text(patient)

    async def show_help(self, group_id: int) -> None:
        await self._reply(group_id, "help_text")
        await self.show_current_menu(group_id)

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
            # Neutral line; menu refresh keeps UI consistent
            await self._reply(patient["group_id"], "unknown_text")
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
        await self.messenger.send_escalation(inst) if hasattr(self.messenger, "send_escalation") else None
        self._escalated.add(inst.dose_key)
        self._log_outcome_csv(inst, "escalated")
        # Keep the invariant "menu is last" after escalation.
        await self.show_current_menu(inst.group_id)

    # ---- confirmation handling ---------------------------------------------------------
    async def _handle_confirmation_text(self, patient: dict) -> None:
        now = self.clock.now()
        target = self.state_mgr.select_target_for_confirmation(now, patient)
        # Only allow confirmation when a dose is actively awaiting.
        if (not target) or (self.state_mgr.status(target) != Status.AWAITING):
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

    # ---- measurement handling ----------------------------------------------------------
    async def _handle_pressure_text(self, patient: dict, text: str) -> None:
        parsed = parse_pressure_free(text)
        gid = patient["group_id"]
        if parsed.get("ok"):
            now_local = self.clock.now()
            sys_v = parsed["sys"]
            dia_v = parsed["dia"]
            pulse_v = parsed.get("pulse")
            vals = (sys_v, dia_v) if pulse_v is None else (sys_v, dia_v, pulse_v)
            self.measures.append_csv(
                "pressure", now_local, patient["patient_id"], patient["patient_label"], vals
            )
            if pulse_v is None:
                await self._reply(gid, "ack_pressure", systolic=sys_v, diastolic=dia_v)
            else:
                await self._reply(
                    gid, "ack_pressure_pulse", systolic=sys_v, diastolic=dia_v, pulse=pulse_v
                )
        else:
            err = parsed.get("error")
            if err == "one_number":
                await self._reply(gid, "err_pressure_one")
            elif err == "range":
                await self._reply(gid, "err_pressure_range")
            else:
                await self._reply(gid, "err_pressure_unrec")

    async def _handle_weight_text(self, patient: dict, text: str) -> None:
        parsed = parse_weight_free(text)
        gid = patient["group_id"]
        if parsed.get("ok"):
            now_local = self.clock.now()
            kg = parsed["kg"]
            self.measures.append_csv(
                "weight", now_local, patient["patient_id"], patient["patient_label"], (kg,)
            )
            await self._reply(gid, "ack_weight", kg=kg)
        else:
            err = parsed.get("error")
            if err == "likely_pressure":
                await self._reply(gid, "err_weight_likely_pressure")
            elif err == "range":
                await self._reply(gid, "err_weight_range")
            else:
                await self._reply(gid, "err_weight_unrec")

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
