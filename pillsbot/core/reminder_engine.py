# pillsbot/core/reminder_engine.py
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
from zoneinfo import ZoneInfo

from pillsbot.core.matcher import Matcher
from pillsbot.core.i18n import fmt, MESSAGES
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
    Orchestrates reminder jobs, callback resolution, and state transitions.
    Messaging (UI/Telegram) and retry timing are delegated to dedicated modules.
    Public API remains compatible with the original tests/specs.
    """

    # ---- lifecycle -------------------------------------------------------------------
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
        self.messenger = ReminderMessenger(
            adapter=self.adapter,
            log=self.log,
            inline_confirm_enabled=getattr(self.cfg, "INLINE_CONFIRM_ENABLED", True),
        )
        # msg_id → DoseKey (for robust inline callback resolution)
        self._msg_to_key: Dict[int, DoseKey] = {}

        # Index lookups
        self.patient_index: Dict[int, dict] = {}  # patient_id → patient dict
        self.group_to_patient: Dict[int, int] = {}  # group_id → patient_id

        # Retry manager wiring (interval/max read from cfg at start time)
        self.retry_mgr: Optional[RetryManager] = None

    def attach_adapter(self, adapter: Any) -> None:
        """
        Attach/replace the transport adapter after construction (solves circular init).
        Ensures the messenger uses the same adapter instance.
        """
        self.adapter = adapter
        self.messenger.adapter = adapter
        self.log.debug("engine.adapter.attached " + kv(kind=type(adapter).__name__))

    async def start(self, scheduler: Any | None) -> None:
        """Prepare indices/state; optionally register jobs with an external scheduler."""
        # Build indices
        for p in getattr(self.cfg, "PATIENTS", []):
            pid = p["patient_id"]
            self.patient_index[pid] = p
            self.group_to_patient[p["group_id"]] = pid
            self.state_mgr.ensure_today_instances(p)

        # Wire retry with current config
        self.retry_mgr = RetryManager(
            interval_seconds=int(getattr(self.cfg, "RETRY_INTERVAL_S", 30)),
            max_attempts=int(getattr(self.cfg, "MAX_RETRY_ATTEMPTS", 3)),
            send_repeat=self._send_repeat_wrapper,
            on_escalate=self._on_escalate_wrapper,
            set_status=self.state_mgr.set_status,
            get_status=self.state_mgr.status,
            logger=self.log,
        )

        # Optionally register jobs with an external scheduler
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
                # Non-fatal if the provided scheduler doesn't support add_job
                pass

    # ---- incoming from adapter --------------------------------------------------------
    async def on_patient_message(self, msg: IncomingMessage) -> None:
        """Main entry for any text from the patient's group."""
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
                    reason="unauthorized or unknown group",
                    group_id=msg.group_id,
                    sender_user_id=msg.sender_user_id,
                )
            )
            return

        patient = self.patient_index[pid]
        text = (msg.text or "").strip()
        low = text.lower()

        # Quick actions via patient keyboard
        if low == MESSAGES["btn_pressure"].lower():
            await self._prompt(patient["group_id"], "prompt_pressure", patient=patient)
            return
        if low == MESSAGES["btn_weight"].lower():
            await self._prompt(patient["group_id"], "prompt_weight", patient=patient)
            return
        if low == MESSAGES["btn_help"].lower():
            await self._reply(patient["group_id"], "help_brief", with_fixed_kb=patient)
            return

        # Measurements: anchored dispatch
        mm = self.measures.match(text)
        if mm:
            mid, body = mm
            parsed = self.measures.parse(mid, body)
            if parsed.get("ok"):
                now_local = self.clock.now()
                self.measures.append_csv(
                    mid, now_local, pid, patient["patient_label"], parsed["values"]
                )
                await self._reply(
                    patient["group_id"],
                    "measure_ack",
                    with_fixed_kb=patient,
                    measure_label=self.measures.get_label(mid),
                )
            else:
                key = (
                    "measure_error_arity"
                    if parsed.get("error") in ("arity", "arity_one")
                    else (
                        "measure_error_one"
                        if parsed.get("error") == "arity_one"
                        else "measure_unknown"
                    )
                )
                await self._reply(patient["group_id"], key, with_fixed_kb=patient)
            return

        # Confirmation via regex patterns
        if self.matcher.matches_confirmation(text):
            await self._handle_confirmation_text(patient)
            return

        # Fallback for unknown input: explicitly say "unknown measure"
        # (tests expect "невідомий показник" to be sent)
        await self._reply(patient["group_id"], "measure_unknown", with_fixed_kb=patient)

    # ---- inline button callback from adapter ------------------------------------------
    async def on_inline_confirm(
        self,
        *,
        group_id: int,
        from_user_id: int,
        data: str,
        message_id: Optional[int] = None,
    ) -> dict:
        """
        Inline button confirm.
        Returns dict for adapter: {'cb_text': str|None, 'show_alert': bool}.
        Resolution order: message_id → payload → selection today.
        """
        expected_pid = self.group_to_patient.get(group_id)
        if expected_pid is None or from_user_id != expected_pid:
            return {"cb_text": fmt("cb_only_patient"), "show_alert": False}

        inst: Optional[DoseInstance] = None

        # 1) Resolve by message_id (authoritative mapping)
        if message_id is not None:
            key = self._msg_to_key.get(message_id)
            if key:
                inst = self.state_mgr.get(key)

        # 2) Parse payload
        if inst is None and data.startswith("confirm:"):
            try:
                _, pid_s, date_s, time_s = data.split(":")
                key = DoseKey(int(pid_s), date_s, time_s)
                inst = self.state_mgr.get(key)
            except Exception:
                pass

        # 3) Fallback: any awaiting/nearest today for this patient
        if inst is None:
            patient = self.patient_index.get(expected_pid)
            if patient:
                inst = self.state_mgr.select_target_for_confirmation(
                    self.clock.now(), patient
                )

        if not inst:
            return {"cb_text": fmt("cb_no_target"), "show_alert": False}

        # Idempotent confirm
        if self.state_mgr.status(inst) == Status.CONFIRMED:
            return {"cb_text": fmt("cb_already_done"), "show_alert": False}

        await self._confirm_and_finalize(inst, source="inline")
        return {"cb_text": fmt("cb_late_ok"), "show_alert": False}

    # ---- jobs / orchestration ----------------------------------------------------------
    async def _start_dose_job(self, *, patient_id: int, time_str: str) -> None:
        """Scheduler entrypoint for a planned dose."""
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
            # Ensure exists
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
                + kv(patient_id=patient_id, time=time_str, reason="already confirmed")
            )
            return

        # Pre-set awaiting FIRST to eliminate tap-before-set race
        self.state_mgr.set_status(inst, Status.AWAITING)
        inst.attempts_sent = 1

        msg_id = await self.messenger.send_reminder(inst, "reminder")
        if msg_id is not None:
            inst.last_message_ids.append(msg_id)
            self._msg_to_key[msg_id] = inst.dose_key

        await self.messenger.refresh_reply_keyboard(patient)
        await self._start_retry(inst)

    # Back-compat alias expected by tests: _measurement_check_job(pid, measure_id)
    async def _measurement_check_job(self, patient_id: int, measure_id: str) -> None:
        await self._job_measure_check(patient_id=patient_id, measure_id=measure_id)

    async def _job_measure_check(self, *, patient_id: int, measure_id: str) -> None:
        """Daily 'missing today' measurement check."""
        patient = self.patient_index.get(patient_id)
        if not patient:
            return
        today = self.clock.now().date()
        if not self.measures.has_today(measure_id, patient_id, today):
            await self._reply(
                patient["group_id"],
                "measure_missing_today",
                with_fixed_kb=patient,
                measure_label=self.measures.get_label(measure_id),
            )

    # ---- retry glue -------------------------------------------------------------------
    async def _start_retry(self, inst: DoseInstance) -> None:
        """Start/replace retry loop task for the given instance."""
        if self.retry_mgr is None:
            return
        await self._stop_retry(inst)  # replace if already running
        inst.retry_task = asyncio.create_task(self.retry_mgr.run(inst))

    async def _stop_retry(self, inst: DoseInstance) -> None:
        t = inst.retry_task
        if t and not t.done():
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        inst.retry_task = None

    async def _send_repeat_wrapper(self, inst: DoseInstance) -> None:
        msg_id = await self.messenger.send_reminder(inst, "repeat")
        if msg_id is not None:
            inst.last_message_ids.append(msg_id)
            self._msg_to_key[msg_id] = inst.dose_key

    async def _on_escalate_wrapper(self, inst: DoseInstance) -> None:
        await self.messenger.send_escalation(inst)
        self._log_outcome_csv(inst, "escalated")

    # ---- confirmation handling ---------------------------------------------------------
    async def _handle_confirmation_text(self, patient: dict) -> None:
        """Text-based confirm; supports preconfirm within grace window."""
        now = self.clock.now()
        target = self.state_mgr.select_target_for_confirmation(now, patient)
        if not target:
            await self._reply(patient["group_id"], "too_early", with_fixed_kb=patient)
            return

        # If pre-confirm within grace interval, confirm immediately with the special ack
        grace_s = int(getattr(self.cfg, "TAKING_GRACE_INTERVAL_S", 600))
        if (
            target.scheduled_dt_local - now <= timedelta(seconds=grace_s)
            and self.state_mgr.status(target) != Status.AWAITING
        ):
            target.preconfirmed = True
            await self._confirm_and_finalize(target, source="preconfirm")
            await self._reply(
                patient["group_id"], "preconfirm_ack", with_fixed_kb=patient
            )
            return

        await self._confirm_and_finalize(target, source="text")
        await self._reply(patient["group_id"], "confirm_ack", with_fixed_kb=patient)

    async def _confirm_and_finalize(self, inst: DoseInstance, *, source: str) -> None:
        """Persistently mark confirmed, stop retry/escalation, and write outcome row."""
        if self.state_mgr.status(inst) == Status.CONFIRMED:
            return
        self.state_mgr.set_status(inst, Status.CONFIRMED)
        await self._stop_retry(inst)
        self.log.info(
            "dose.confirm "
            + kv(patient_id=inst.patient_id, time=inst.dose_key.time_str, source=source)
        )
        self._log_outcome_csv(inst, "confirmed")

    # ---- messaging shims (keep engine free of Telegram specifics) ---------------------
    async def _reply(
        self,
        group_id: int,
        template_key: str,
        *,
        with_fixed_kb: Optional[dict] = None,
        **fmt_args: Any,
    ) -> Optional[int]:
        """Send a group message using i18n template; optionally attach fixed reply kb."""
        msg_id = await self.messenger.send_group_template(
            group_id, template_key, **fmt_args
        )
        if with_fixed_kb is not None:
            await self.messenger.refresh_reply_keyboard(with_fixed_kb)
        return msg_id

    async def _prompt(self, group_id: int, template_key: str, *, patient: dict) -> None:
        """Send a small prompt and surface the ForceReply/keyboard if available."""
        await self._reply(group_id, template_key, with_fixed_kb=patient)

    # ---- tiny sugar -------------------------------------------------------------------
    def _today_str(self) -> str:
        return self.clock.today_str()

    # ---- outcome CSV ------------------------------------------------------------------
    def _log_outcome_csv(self, inst: DoseInstance, status: str) -> None:
        """Append a one-line outcome row into the configured CSV (analytics/audit)."""
        line = (
            f"{inst.scheduled_dt_local.strftime('%Y-%m-%d %H:%M')}, "
            f"{inst.patient_id}, {inst.patient_label}, {inst.pill_text}, {status}, {inst.attempts_sent}\n"
        )
        path = getattr(self.cfg, "LOG_FILE", "pillsbot/logs/pills.csv")
        import os

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    # ---- backwards-compat for tests ---------------------------------------------------
    @property
    def state(self):
        """Expose the raw state mapping for test compatibility."""
        return self.state_mgr.mapping


# Re-export for backwards compatibility
__all__ = ["ReminderEngine", "IncomingMessage", "Status", "DoseKey", "DoseInstance"]
