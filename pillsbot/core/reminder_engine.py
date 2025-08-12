# pillsbot/core/reminder_engine.py
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any, List
from zoneinfo import ZoneInfo
import os

from pillsbot.core.matcher import Matcher
from pillsbot.core.i18n import fmt, MESSAGES
from pillsbot.core.logging_utils import kv
from pillsbot.core.measurements import MeasurementRegistry
from pillsbot.core.config_validation import validate_config


@dataclass(frozen=True)
class DoseKey:
    patient_id: int
    date_str: str  # YYYY-MM-DD
    time_str: str  # HH:MM


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
    # v3: keep message_ids of reminders/retries (for trace/debug; no edits performed)
    last_message_ids: List[int] = field(default_factory=list)


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

        # Measurement registry
        measures_cfg = getattr(config, "MEASURES", {}) or {}
        self.measures = MeasurementRegistry(self.tz, measures_cfg)

        self.state: Dict[DoseKey, DoseInstance] = {}
        self.group_to_patient: Dict[int, int] = {
            p["group_id"]: p["patient_id"] for p in config.PATIENTS
        }
        self.patient_index: Dict[int, dict] = {
            p["patient_id"]: p for p in config.PATIENTS
        }

        os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
        os.makedirs(
            os.path.dirname(getattr(config, "AUDIT_LOG_FILE", "pillsbot/logs")),
            exist_ok=True,
        )

        self.log = logging.getLogger("pillsbot.engine")

    # --- CSV outcome log (flat file analytics; stays separate from audit log) ---
    def _log_outcome_csv(
        self,
        when_local: datetime,
        patient_id: int,
        patient_label: str,
        pill_text: str,
        status: str,
        attempts: int,
    ) -> None:
        line = (
            f"{when_local.strftime('%Y-%m-%d %H:%M')}, "
            f"{patient_id}, {patient_label}, {pill_text}, {status}, {attempts}\n"
        )
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
        """Ensure today's dose instances exist; prune older-day instances."""
        today = self._today_str()

        # prune anything not from today to prevent unbounded growth
        if self.state:
            to_keep: Dict[DoseKey, DoseInstance] = {
                k: v for k, v in self.state.items() if k.date_str == today
            }
            if len(to_keep) != len(self.state):
                self.log.debug(
                    "state.prune " + kv(removed=len(self.state) - len(to_keep))
                )
            self.state = to_keep

        # (re)create today's instances
        for p in self.cfg.PATIENTS:
            for d in p["doses"]:
                key = self._get_dosekey(p["patient_id"], today, d["time"])
                if key not in self.state:
                    hh, mm = map(int, d["time"].split(":"))
                    sched = datetime.now(self.tz).replace(
                        hour=hh, minute=mm, second=0, microsecond=0
                    )
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
                    # Creation is not messaging → DEBUG
                    self.log.debug(
                        "state.instance.create "
                        + kv(
                            patient_id=inst.patient_id,
                            time=d["time"],
                            text=inst.pill_text,
                            status=inst.status,
                        )
                    )

    def _set_status(self, inst: DoseInstance, new_status: str, reason: str) -> None:
        old = inst.status
        inst.status = new_status
        # State/status changes → DEBUG
        self.log.debug(
            "state.status.change "
            + kv(
                patient_id=inst.patient_id,
                time=inst.dose_key.time_str,
                from_status=old,
                to_status=new_status,
                reason=reason,
            )
        )

    async def start(self, scheduler) -> None:
        """Prepare state and install daily jobs into the APScheduler."""
        # Validate configuration before installing any jobs
        validate_config(self.cfg)

        self._ensure_today_instances()

        installed = []
        # Dose jobs (existing)
        for p in self.cfg.PATIENTS:
            for d in p["doses"]:
                hh, mm = map(int, d["time"].split(":"))
                job_id = f"dose_{p['patient_id']}_{d['time']}"
                scheduler.add_job(
                    self._start_dose_job,
                    trigger="cron",
                    hour=hh,
                    minute=mm,
                    timezone=self.tz,
                    args=[p["patient_id"], d["time"]],
                    id=job_id,
                    replace_existing=True,
                )
                # Job creation → DEBUG
                self.log.debug(
                    "job.install "
                    + kv(
                        job_id=job_id,
                        patient_id=p["patient_id"],
                        time=d["time"],
                        text=d["text"],
                    )
                )
                installed.append(
                    dict(
                        job_id=job_id,
                        patient_id=p["patient_id"],
                        time=d["time"],
                        text=d["text"],
                    )
                )

        # Measurement daily checks (per patient–measure when configured)
        for p in self.cfg.PATIENTS:
            checks = p.get("measurement_checks", []) or []
            for chk in checks:
                mid = chk.get("measure_id")
                t = chk.get("time")
                if not mid or mid not in self.measures.available():
                    self.log.debug(
                        "mcheck.skip "
                        + kv(
                            patient_id=p["patient_id"],
                            measure_id=mid,
                            reason="unknown measure",
                        )
                    )
                    continue
                hh, mm = map(int, t.split(":"))
                job_id = f"measure_check:{p['patient_id']}:{mid}:{t}"
                scheduler.add_job(
                    self._measurement_check_job,
                    trigger="cron",
                    hour=hh,
                    minute=mm,
                    timezone=self.tz,
                    args=[p["patient_id"], mid],
                    id=job_id,
                    replace_existing=True,
                )
                self.log.debug(
                    "job.install "
                    + kv(
                        job_id=job_id,
                        patient_id=p["patient_id"],
                        measure_id=mid,
                        time=t,
                    )
                )
                installed.append(
                    dict(
                        job_id=job_id,
                        patient_id=p["patient_id"],
                        time=t,
                        text=f"check {mid}",
                    )
                )

        # startup.* → INFO (trace all installed cron jobs)
        for j in installed:
            self.log.info(
                "startup.cron "
                + kv(
                    job_id=j["job_id"],
                    patient_id=j["patient_id"],
                    time=j["time"],
                    text=j["text"],
                )
            )

    async def _start_dose_job(self, patient_id: int, time_str: str) -> None:
        """Called by scheduler at dose time in Europe/Kyiv."""
        # Triggering is not messaging → DEBUG
        self.log.debug("job.trigger " + kv(patient_id=patient_id, time=time_str))

        self._ensure_today_instances()
        key = self._get_dosekey(patient_id, self._today_str(), time_str)
        inst = self.state.get(key)
        if not inst:
            self.log.debug(
                "job.trigger.miss " + kv(patient_id=patient_id, time=time_str)
            )
            return
        if inst.status == "Confirmed":
            self.log.debug(
                "job.trigger.skip "
                + kv(patient_id=patient_id, time=time_str, reason="already confirmed")
            )
            return  # preconfirmed earlier

        # First reminder (v3: attach inline confirm button)
        kb_inline = self.adapter.build_confirm_inline_kb(inst.dose_key)
        msg_id = await self.adapter.send_group_message(
            inst.group_id,
            fmt("reminder", pill_text=inst.pill_text),
            reply_markup=kb_inline,
        )
        inst.last_message_ids.append(msg_id)

        self._set_status(inst, "AwaitingConfirmation", reason="first reminder sent")
        inst.attempts_sent = 1

        inst.retry_task = asyncio.create_task(self._retry_loop(inst))
        self.log.debug(
            "job.retry.start "
            + kv(
                patient_id=inst.patient_id,
                time=time_str,
                interval_s=self.cfg.RETRY_INTERVAL_S,
            )
        )

    async def _retry_loop(self, inst: DoseInstance) -> None:
        I = self.cfg.RETRY_INTERVAL_S  # noqa: E741
        N = self.cfg.MAX_RETRY_ATTEMPTS
        while inst.status == "AwaitingConfirmation":
            await asyncio.sleep(I)
            if inst.status != "AwaitingConfirmation":
                break
            if inst.attempts_sent < N:
                # Repeat reminder with inline button again
                kb_inline = self.adapter.build_confirm_inline_kb(inst.dose_key)
                msg_id = await self.adapter.send_group_message(
                    inst.group_id, fmt("repeat_reminder"), reply_markup=kb_inline
                )
                inst.last_message_ids.append(msg_id)
                inst.attempts_sent += 1
                self.log.debug(
                    "job.retry.tick "
                    + kv(
                        patient_id=inst.patient_id,
                        time=inst.dose_key.time_str,
                        attempt=inst.attempts_sent,
                    )
                )
            else:
                # Escalation: no new inline buttons here; keep existing ones on prior messages
                kb_fixed = self.adapter.build_patient_reply_kb(
                    self.patient_index[inst.patient_id]
                )
                await self.adapter.send_group_message(
                    inst.group_id, fmt("escalate_group"), reply_markup=kb_fixed
                )
                when = inst.scheduled_dt_local
                date = when.strftime("%Y-%m-%d")
                time = when.strftime("%H:%M")
                await self.adapter.send_nurse_dm(
                    inst.nurse_user_id,
                    fmt(
                        "escalate_dm",
                        patient_label=inst.patient_label,
                        date=date,
                        time=time,
                        pill_text=inst.pill_text,
                    ),
                )
                self._set_status(inst, "Escalated", reason="max retries exceeded")
                self._log_outcome_csv(
                    inst.scheduled_dt_local,
                    inst.patient_id,
                    inst.patient_label,
                    inst.pill_text,
                    "Escalated",
                    inst.attempts_sent,
                )
                self.log.debug(
                    "job.retry.stop "
                    + kv(
                        patient_id=inst.patient_id,
                        time=inst.dose_key.time_str,
                        reason="escalated",
                    )
                )
                break

    async def _measurement_check_job(self, patient_id: int, measure_id: str) -> None:
        """Daily check for missing measurement (group message only)."""
        self.log.debug(
            "job.trigger "
            + kv(kind="measure_check", patient_id=patient_id, measure_id=measure_id)
        )
        patient = self.patient_index.get(patient_id)
        if not patient:
            self.log.debug(
                "job.trigger.miss "
                + kv(reason="unknown patient", patient_id=patient_id)
            )
            return

        today = self._local_now().date()
        if not self.measures.has_today(measure_id, patient_id, today):
            label = self.measures.get_label(measure_id)
            kb_fixed = self.adapter.build_patient_reply_kb(patient)
            await self.adapter.send_group_message(
                patient["group_id"],
                fmt("measure_missing_today", measure_label=label),
                reply_markup=kb_fixed,
            )
            self.log.info(
                "msg.engine.reply "
                + kv(
                    group_id=patient["group_id"],
                    template="measure_missing_today",
                    measure_id=measure_id,
                )
            )

    # --- Incoming messages from adapter ---
    async def on_patient_message(self, msg: IncomingMessage) -> None:
        # Engine-level inbound (messaging → INFO)
        self.log.info(
            "msg.engine.in "
            + kv(
                group_id=msg.group_id, sender_user_id=msg.sender_user_id, text=msg.text
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

        # 0) v3: Button-driven flows (before measurement parsing)
        low = text.lower()
        if low == MESSAGES["btn_pressure"].lower():
            await self.adapter.send_group_message(
                patient["group_id"],
                fmt("prompt_pressure"),
                reply_markup=self.adapter.build_force_reply(),
            )
            self.log.info(
                "msg.engine.reply "
                + kv(group_id=patient["group_id"], template="prompt_pressure")
            )
            return
        if low == MESSAGES["btn_weight"].lower():
            await self.adapter.send_group_message(
                patient["group_id"],
                fmt("prompt_weight"),
                reply_markup=self.adapter.build_force_reply(),
            )
            self.log.info(
                "msg.engine.reply "
                + kv(group_id=patient["group_id"], template="prompt_weight")
            )
            return
        if low == MESSAGES["btn_help"].lower():
            kb_fixed = self.adapter.build_patient_reply_kb(patient)
            await self.adapter.send_group_message(
                patient["group_id"], fmt("help_brief"), reply_markup=kb_fixed
            )
            self.log.info(
                "msg.engine.reply "
                + kv(group_id=patient["group_id"], template="help_brief")
            )
            return

        # 1) Measurements (start-anchored)
        m = self.measures.match(text)
        if m:
            mid, body = m
            parsed = self.measures.parse(mid, body)
            if parsed.get("ok"):
                now_local = self._local_now()
                self.measures.append_csv(
                    mid, now_local, pid, patient["patient_label"], parsed["values"]
                )
                kb_fixed = self.adapter.build_patient_reply_kb(patient)
                await self.adapter.send_group_message(
                    patient["group_id"],
                    fmt("measure_ack", measure_label=self.measures.get_label(mid)),
                    reply_markup=kb_fixed,
                )
                self.log.info(
                    "msg.engine.reply "
                    + kv(
                        group_id=patient["group_id"],
                        template="measure_ack",
                        measure_id=mid,
                    )
                )
            else:
                # Choose error message per parser_kind
                md = self.measures.measures[mid]
                kb_fixed = self.adapter.build_patient_reply_kb(patient)
                if md.parser_kind == "int3":
                    await self.adapter.send_group_message(
                        patient["group_id"],
                        fmt("measure_error_arity", expected=3),
                        reply_markup=kb_fixed,
                    )
                    template = "measure_error_arity"
                else:
                    await self.adapter.send_group_message(
                        patient["group_id"],
                        fmt("measure_error_one"),
                        reply_markup=kb_fixed,
                    )
                    template = "measure_error_one"
                self.log.info(
                    "msg.engine.reply "
                    + kv(
                        group_id=patient["group_id"],
                        template=template,
                        measure_id=mid,
                    )
                )
            return

        # 2) Confirmations (existing semantics; search-anywhere)
        if not self.matcher.matches_confirmation(text):
            # 3) Unknown indicator (neither measurement nor confirmation)
            kb_fixed = self.adapter.build_patient_reply_kb(patient)
            await self.adapter.send_group_message(
                patient["group_id"], fmt("measure_unknown"), reply_markup=kb_fixed
            )
            self.log.info(
                "msg.engine.reply "
                + kv(group_id=patient["group_id"], template="measure_unknown")
            )
            return

        now_local = self._local_now()
        today = self._today_str()

        # Determine target dose
        upcoming: Optional[DoseInstance] = None
        min_dt = None
        for d in patient["doses"]:
            key = self._get_dosekey(pid, today, d["time"])
            inst = self.state.get(key)
            if not inst or inst.status in ("Confirmed", "Escalated"):
                continue
            dt = inst.scheduled_dt_local
            if dt >= now_local and (min_dt is None or dt < min_dt):
                upcoming = inst
                min_dt = dt

        awaiting_now: Optional[DoseInstance] = None
        for d in patient["doses"]:
            key = self._get_dosekey(pid, today, d["time"])
            inst = self.state.get(key)
            if inst and inst.status == "AwaitingConfirmation":
                awaiting_now = inst
                break

        target = awaiting_now or upcoming

        if target is None:
            kb_fixed = self.adapter.build_patient_reply_kb(patient)
            await self.adapter.send_group_message(
                patient["group_id"], fmt("too_early"), reply_markup=kb_fixed
            )
            self.log.info(
                "msg.engine.reply "
                + kv(
                    group_id=patient["group_id"],
                    template="too_early",
                    reason="no target dose",
                )
            )
            return

        if target.status == "AwaitingConfirmation":
            if target.retry_task and not target.retry_task.done():
                target.retry_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await target.retry_task
                self.log.debug(
                    "job.retry.cancel "
                    + kv(patient_id=target.patient_id, time=target.dose_key.time_str)
                )
            self._set_status(target, "Confirmed", reason="patient confirmed")
            self._log_outcome_csv(
                target.scheduled_dt_local,
                target.patient_id,
                target.patient_label,
                target.pill_text,
                "OK",
                target.attempts_sent,
            )
            kb_fixed = self.adapter.build_patient_reply_kb(patient)
            await self.adapter.send_group_message(
                target.group_id, fmt("confirm_ack"), reply_markup=kb_fixed
            )
            self.log.info(
                "msg.engine.reply "
                + kv(group_id=target.group_id, template="confirm_ack")
            )
            return

        # Preconfirm path
        delta = (target.scheduled_dt_local - now_local).total_seconds()
        if 0 <= delta <= self.cfg.TAKING_GRACE_INTERVAL_S:
            self._set_status(target, "Confirmed", reason="preconfirm within grace")
            target.preconfirmed = True
            target.attempts_sent = 0
            self._log_outcome_csv(
                target.scheduled_dt_local,
                target.patient_id,
                target.patient_label,
                target.pill_text,
                "OK",
                0,
            )
            kb_fixed = self.adapter.build_patient_reply_kb(patient)
            await self.adapter.send_group_message(
                target.group_id, fmt("preconfirm_ack"), reply_markup=kb_fixed
            )
            self.log.info(
                "msg.engine.reply "
                + kv(group_id=target.group_id, template="preconfirm_ack")
            )
        else:
            kb_fixed = self.adapter.build_patient_reply_kb(patient)
            await self.adapter.send_group_message(
                target.group_id, fmt("too_early"), reply_markup=kb_fixed
            )
            self.log.info(
                "msg.engine.reply "
                + kv(
                    group_id=target.group_id,
                    template="too_early",
                    reason="outside grace",
                )
            )

    # --- Inline confirmation callback entry (v3) ---
    async def on_inline_confirm(
        self, group_id: int, from_user_id: int, data: str
    ) -> dict:
        """
        Process inline 'confirm taken' button presses.

        Returns a dict like {"cb_text": "...", "show_alert": False} for the adapter
        to answer the callback ephemerally. On success, we send normal group acks and
        keep the callback silent (cb_text=None).
        """
        # Validate group ↔ patient mapping and payload
        expected_pid = self.group_to_patient.get(group_id)
        if expected_pid is None or from_user_id != expected_pid:
            # Someone else pressed the button in the group
            return {"cb_text": fmt("cb_only_patient"), "show_alert": False}

        parts = (data or "").split(":")
        if len(parts) != 4 or parts[0] != "confirm":
            return {"cb_text": fmt("cb_no_target"), "show_alert": False}

        try:
            pid = int(parts[1])
            date_s = parts[2]
            time_s = parts[3]
        except Exception:
            return {"cb_text": fmt("cb_no_target"), "show_alert": False}

        if pid != expected_pid:
            return {"cb_text": fmt("cb_no_target"), "show_alert": False}

        key = DoseKey(pid, date_s, time_s)
        inst = self.state.get(key)
        if not inst:
            return {"cb_text": fmt("cb_no_target"), "show_alert": False}

        if inst.status == "Confirmed":
            return {"cb_text": fmt("cb_already_done"), "show_alert": False}

        if inst.status not in ("AwaitingConfirmation", "Escalated"):
            # No actionable state
            return {"cb_text": fmt("cb_no_target"), "show_alert": False}

        # Confirm now
        previous_status = inst.status

        if inst.retry_task and not inst.retry_task.done():
            inst.retry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await inst.retry_task
            self.log.debug(
                "job.retry.cancel "
                + kv(patient_id=inst.patient_id, time=inst.dose_key.time_str)
            )

        self._set_status(inst, "Confirmed", reason="inline button")
        self._log_outcome_csv(
            inst.scheduled_dt_local,
            inst.patient_id,
            inst.patient_label,
            inst.pill_text,
            "OK",
            inst.attempts_sent,
        )

        # Group ack with fixed reply keyboard
        patient = self.patient_index.get(inst.patient_id)
        kb_fixed = self.adapter.build_patient_reply_kb(patient)
        await self.adapter.send_group_message(
            inst.group_id, fmt("confirm_ack"), reply_markup=kb_fixed
        )

        # Optionally notify nurse if confirmation came after escalation
        if previous_status == "Escalated":
            # Keep text concise; i18n key not required by spec (optional DM).
            msg = f"Пізнє підтвердження: {inst.patient_label} за {inst.dose_key.date_str} {inst.dose_key.time_str} — OK."
            await self.adapter.send_nurse_dm(inst.nurse_user_id, msg)

        # Silent callback OK
        return {"cb_text": None, "show_alert": False}
