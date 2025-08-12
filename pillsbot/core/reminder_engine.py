# pillsbot/core/reminder_engine.py
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Any, List, Tuple
from zoneinfo import ZoneInfo
import os

from pillsbot.core.matcher import Matcher
from pillsbot.core.i18n import fmt, MESSAGES
from pillsbot.core.logging_utils import kv
from pillsbot.core.measurements import MeasurementRegistry
from pillsbot.core.config_validation import validate_config


# --------------------------------------------------------------------------------------
# Public data structures kept here so other modules (adapters) don't need to change
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DoseKey:
    patient_id: int
    date_str: str  # YYYY-MM-DD (engine-local string)
    time_str: str  # HH:MM


@dataclass
class IncomingMessage:
    group_id: int
    sender_user_id: int
    text: str
    sent_at_utc: datetime


# --------------------------------------------------------------------------------------
# Internal helpers / small types
# --------------------------------------------------------------------------------------
class Status(Enum):
    """Internal status enum; stored as strings on instances for compatibility."""

    PENDING = "Pending"
    AWAITING = "AwaitingConfirmation"
    CONFIRMED = "Confirmed"
    ESCALATED = "Escalated"


@dataclass
class DoseInstance:
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
    last_message_ids: List[int] = field(default_factory=list)  # debug/trace only


class Clock:
    """Injectable time source (simple & testable)."""

    def __init__(self, tz: ZoneInfo):
        self.tz = tz

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def today_str(self) -> str:
        return self.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------------------
# ReminderEngine
# --------------------------------------------------------------------------------------
class ReminderEngine:
    """
    v3 engine, refactored to be simpler & more debuggable:
    - explicit helpers for state/retry/selection/replies
    - status via small Enum (stored as strings for compatibility)
    - inline-callback resolution by message_id (robust) with fallbacks
    Public API unchanged; plus legacy test shims for *_job names.
    """

    # ---- lifecycle -------------------------------------------------------------------
    def __init__(self, config: Any, adapter: Any, clock: Optional[Clock] = None):
        self.cfg = config
        self.adapter = adapter
        self.tz: ZoneInfo = config.TZ
        self.clock = clock or Clock(self.tz)

        # Natural language bits
        self.matcher = Matcher(config.CONFIRM_PATTERNS)

        # Measurements
        measures_cfg = getattr(config, "MEASURES", {}) or {}
        self.measures = MeasurementRegistry(self.tz, measures_cfg)

        # State
        self.state: Dict[DoseKey, DoseInstance] = {}
        self.group_to_patient: Dict[int, int] = {
            p["group_id"]: p["patient_id"] for p in config.PATIENTS
        }
        self.patient_index: Dict[int, dict] = {
            p["patient_id"]: p for p in config.PATIENTS
        }

        # Map sent Telegram message_id -> DoseKey (for robust inline callback resolution)
        self.msg_to_key: Dict[int, DoseKey] = {}

        # Filesystem
        os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
        os.makedirs(
            os.path.dirname(getattr(config, "AUDIT_LOG_FILE", "pillsbot/logs")),
            exist_ok=True,
        )

        # Logging
        self.log = logging.getLogger("pillsbot.engine")

    async def start(self, scheduler) -> None:
        """Validate config, seed today's state, and install recurring jobs."""
        validate_config(self.cfg)
        self._ensure_today_instances()

        installed: List[dict] = []
        # Dose jobs
        for p in self.cfg.PATIENTS:
            for d in p["doses"]:
                hh, mm = map(int, d["time"].split(":"))
                job_id = f"dose_{p['patient_id']}_{d['time']}"
                scheduler.add_job(
                    self._job_start_dose,
                    trigger="cron",
                    hour=hh,
                    minute=mm,
                    timezone=self.tz,
                    args=[p["patient_id"], d["time"]],
                    id=job_id,
                    replace_existing=True,
                )
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

        # Measurement checks
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
                    self._job_measure_check,
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

        # Single INFO line per job on startup for visibility
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

        # Button flows (compare via i18n keys)
        if low == MESSAGES["btn_pressure"].lower():
            await self._prompt(patient["group_id"], "prompt_pressure", patient)
            return
        if low == MESSAGES["btn_weight"].lower():
            await self._prompt(patient["group_id"], "prompt_weight", patient)
            return
        if low == MESSAGES["btn_help"].lower():
            await self._reply(patient["group_id"], "help_brief", with_fixed_kb=patient)
            return

        # Measurements (anchored)
        mm = self.measures.match(text)
        if mm:
            mid, body = mm
            parsed = self.measures.parse(mid, body)
            if parsed.get("ok"):
                now_local = self._now()
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
                md = self.measures.measures[mid]
                if md.parser_kind == "int3":
                    await self._reply(
                        patient["group_id"],
                        "measure_error_arity",
                        with_fixed_kb=patient,
                        expected=3,
                    )
                else:
                    await self._reply(
                        patient["group_id"], "measure_error_one", with_fixed_kb=patient
                    )
            return

        # Confirmation (free text)
        if not self.matcher.matches_confirmation(text):
            await self._reply(
                patient["group_id"], "measure_unknown", with_fixed_kb=patient
            )
            return

        # Map confirmation → a target dose
        now = self._now()
        target = self._select_target_for_confirmation(now, patient)
        if target is None:
            await self._reply(patient["group_id"], "too_early", with_fixed_kb=patient)
            return

        if self._status(target) == Status.AWAITING:
            await self._confirm_and_ack(target, patient, reason="patient confirmed")
            return

        # Preconfirm path (within grace)
        delta = (target.scheduled_dt_local - now).total_seconds()
        if 0 <= delta <= self.cfg.TAKING_GRACE_INTERVAL_S:
            self._set_status(target, Status.CONFIRMED, reason="preconfirm within grace")
            target.preconfirmed = True
            target.attempts_sent = 0
            self._log_outcome_csv(target, status="OK")
            await self._reply(target.group_id, "preconfirm_ack", with_fixed_kb=patient)
        else:
            await self._reply(target.group_id, "too_early", with_fixed_kb=patient)

    async def on_inline_confirm(
        self,
        group_id: int,
        from_user_id: int,
        data: str,
        message_id: Optional[int] = None,
    ) -> dict:
        """
        Inline button confirm.
        Returns dict for adapter: {'cb_text': str|None, 'show_alert': bool}.
        Resolution order: message_id → payload → any awaiting/escalated today.
        """
        expected_pid = self.group_to_patient.get(group_id)
        if expected_pid is None or from_user_id != expected_pid:
            return {"cb_text": fmt("cb_only_patient"), "show_alert": False}

        inst: Optional[DoseInstance] = None

        # 1) Resolve by message_id first (authoritative mapping)
        if message_id is not None:
            key = self.msg_to_key.get(message_id)
            if key:
                inst = self.state.get(key)
                if inst is None:
                    self.log.debug(
                        "cb.resolve.msgid.miss "
                        + kv(message_id=message_id, reason="key pruned")
                    )
                else:
                    self.log.debug(
                        "cb.resolve.msgid.hit "
                        + kv(
                            message_id=message_id,
                            patient_id=key.patient_id,
                            time=key.time_str,
                        )
                    )

        # 2) Fallback by payload (pid/date/time)
        if inst is None:
            parts = (data or "").split(":")
            if len(parts) == 4 and parts[0] == "confirm":
                try:
                    pid = int(parts[1])
                    date_s = parts[2]
                    time_s = parts[3]
                except Exception:
                    pid = -1
                    date_s = ""
                    time_s = ""
                if pid == expected_pid:
                    inst = self.state.get(DoseKey(pid, date_s, time_s))
                    if inst:
                        self.log.debug(
                            "cb.resolve.payload.hit "
                            + kv(patient_id=pid, date=date_s, time=time_s)
                        )
                    else:
                        self.log.debug(
                            "cb.resolve.payload.miss "
                            + kv(patient_id=pid, date=date_s, time=time_s)
                        )

        # 3) Last resort: any AWAITING/ESCALATED for this patient today with same time (or any awaiting)
        if inst is None:
            today = self._today_str()
            time_guess = None
            parts = (data or "").split(":")
            if len(parts) == 4 and parts[0] == "confirm":
                time_guess = parts[3]
            for k, v in self.state.items():
                if (
                    k.patient_id == expected_pid
                    and k.date_str == today
                    and self._status(v) in (Status.AWAITING, Status.ESCALATED)
                ):
                    if time_guess is None or k.time_str == time_guess:
                        inst = v
                        self.log.debug(
                            "cb.resolve.fallback.hit "
                            + kv(
                                patient_id=k.patient_id,
                                date=k.date_str,
                                time=k.time_str,
                            )
                        )
                        break

        if inst is None:
            return {"cb_text": fmt("cb_no_target"), "show_alert": False}

        status = self._status(inst)
        if status == Status.CONFIRMED:
            return {"cb_text": fmt("cb_already_done"), "show_alert": False}
        if status not in (Status.AWAITING, Status.ESCALATED):
            return {"cb_text": fmt("cb_no_target"), "show_alert": False}

        previous = status
        patient = self.patient_index.get(inst.patient_id)
        await self._confirm_and_ack(inst, patient, reason="inline button")
        if previous == Status.ESCALATED:
            msg = f"Пізнє підтвердження: {inst.patient_label} за {inst.dose_key.date_str} {inst.dose_key.time_str} — OK."
            await self.adapter.send_nurse_dm(inst.nurse_user_id, msg)

        return {"cb_text": None, "show_alert": False}

    # ---- jobs (scheduler) -------------------------------------------------------------
    async def _job_start_dose(self, patient_id: int, time_str: str) -> None:
        """Scheduler entry: set awaiting, send first reminder, refresh keyboard, start retry loop."""
        self.log.debug("job.trigger " + kv(patient_id=patient_id, time=time_str))
        self._ensure_today_instances()

        key = self._dosekey_today(patient_id, time_str)
        inst = self.state.get(key)
        if not inst:
            self.log.debug(
                "job.trigger.miss " + kv(patient_id=patient_id, time=time_str)
            )
            return
        if self._status(inst) == Status.CONFIRMED:
            self.log.debug(
                "job.trigger.skip "
                + kv(patient_id=patient_id, time=time_str, reason="already confirmed")
            )
            return

        # Pre-set awaiting FIRST to eliminate tap-before-set race
        self._set_status(inst, Status.AWAITING, reason="first reminder pre-set")
        inst.attempts_sent = 1

        await self._send_reminder(inst, "reminder")
        await self._refresh_reply_kb(self.patient_index[inst.patient_id])
        await self._start_retry(inst)

    async def _job_measure_check(self, patient_id: int, measure_id: str) -> None:
        """Scheduler entry: daily 'missing today' measurement check."""
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
        today = self._now().date()
        if not self.measures.has_today(measure_id, patient_id, today):
            label = self.measures.get_label(measure_id)
            await self._reply(
                patient["group_id"],
                "measure_missing_today",
                with_fixed_kb=patient,
                measure_label=label,
            )

    # ---------- Legacy test shims (compat wrappers to keep tests green) ----------------
    async def _start_dose_job(self, patient_id: int, time_str: str) -> None:
        """Compatibility wrapper for older tests."""
        await self._job_start_dose(patient_id, time_str)

    async def _measurement_check_job(self, patient_id: int, measure_id: str) -> None:
        """Compatibility wrapper for older tests."""
        await self._job_measure_check(patient_id, measure_id)

    # ---- retry management -------------------------------------------------------------
    async def _start_retry(self, inst: DoseInstance) -> None:
        """Start the retry loop for a dose (idempotent)."""
        self._stop_retry(inst)  # just in case
        inst.retry_task = asyncio.create_task(self._retry_loop(inst))
        self.log.debug(
            "job.retry.start "
            + kv(
                patient_id=inst.patient_id,
                time=inst.dose_key.time_str,
                interval_s=self.cfg.RETRY_INTERVAL_S,
            )
        )

    def _stop_retry(self, inst: DoseInstance) -> None:
        """Cancel a running retry task if present."""
        if inst.retry_task and not inst.retry_task.done():
            inst.retry_task.cancel()

    async def _retry_loop(self, inst: DoseInstance) -> None:
        """Retry loop: send repeats up to N, then escalate."""
        I = self.cfg.RETRY_INTERVAL_S
        N = self.cfg.MAX_RETRY_ATTEMPTS
        try:
            while self._status(inst) == Status.AWAITING:
                await asyncio.sleep(I)
                if self._status(inst) != Status.AWAITING:
                    break
                if inst.attempts_sent < N:
                    await self._send_reminder(inst, "repeat_reminder")
                    await self._refresh_reply_kb(self.patient_index[inst.patient_id])
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
                    await self._escalate(inst)
                    break
        except asyncio.CancelledError:
            self.log.debug(
                "job.retry.cancel "
                + kv(patient_id=inst.patient_id, time=inst.dose_key.time_str)
            )
            raise

    async def _escalate(self, inst: DoseInstance) -> None:
        """Escalate to nurse after max retries; keep existing inline buttons on prior messages."""
        patient = self.patient_index[inst.patient_id]
        kb_fixed = None
        # Build keyboard only if adapter provides it (tests' FakeAdapter might not)
        if hasattr(self.adapter, "build_patient_reply_kb"):
            try:
                kb_fixed = self.adapter.build_patient_reply_kb(patient)
            except Exception as e:
                self.log.debug(
                    "kb.build.error " + kv(group_id=patient.get("group_id"), err=str(e))
                )
        await self._send_group(
            inst.group_id, fmt("escalate_group"), reply_markup=kb_fixed
        )

        when = inst.scheduled_dt_local
        await self.adapter.send_nurse_dm(
            inst.nurse_user_id,
            fmt(
                "escalate_dm",
                patient_label=inst.patient_label,
                date=when.strftime("%Y-%m-%d"),
                time=when.strftime("%H:%M"),
                pill_text=inst.pill_text,
            ),
        )

        self._set_status(inst, Status.ESCALATED, reason="max retries exceeded")
        self._log_outcome_csv(inst, status="Escalated")
        self.log.debug(
            "job.retry.stop "
            + kv(
                patient_id=inst.patient_id,
                time=inst.dose_key.time_str,
                reason="escalated",
            )
        )

    # ---- selection / confirmation -----------------------------------------------------
    def _select_target_for_confirmation(
        self, now: datetime, patient: dict
    ) -> Optional[DoseInstance]:
        """Prefer the actively waiting dose; otherwise the nearest upcoming (same day)."""
        pid = patient["patient_id"]
        today = self._today_str()

        # 1) Actively waiting
        for d in patient["doses"]:
            key = DoseKey(pid, today, d["time"])
            inst = self.state.get(key)
            if inst and self._status(inst) == Status.AWAITING:
                return inst

        # 2) Nearest upcoming today (not confirmed/escalated)
        best: Tuple[Optional[DoseInstance], Optional[datetime]] = (None, None)
        for d in patient["doses"]:
            key = DoseKey(pid, today, d["time"])
            inst = self.state.get(key)
            if not inst or self._status(inst) in (Status.CONFIRMED, Status.ESCALATED):
                continue
            dt = inst.scheduled_dt_local
            if dt >= now and (best[1] is None or dt < best[1]):
                best = (inst, dt)
        return best[0]

    async def _confirm_and_ack(
        self, inst: DoseInstance, patient: dict, reason: str
    ) -> None:
        """Confirm a dose, stop retry loop, log outcome, and send ack with fixed keyboard."""
        if inst.retry_task and not inst.retry_task.done():
            with contextlib.suppress(asyncio.CancelledError):
                self._stop_retry(inst)
                await inst.retry_task
        self._set_status(inst, Status.CONFIRMED, reason=reason)
        self._log_outcome_csv(inst, status="OK")
        await self._reply(inst.group_id, "confirm_ack", with_fixed_kb=patient)

    # ---- state management -------------------------------------------------------------
    def _ensure_today_instances(self) -> None:
        """Prune old instances and (re)create today's. Also prune msg→key map."""
        today = self._today_str()

        # prune non-today
        if self.state:
            kept: Dict[DoseKey, DoseInstance] = {
                k: v for k, v in self.state.items() if k.date_str == today
            }
            if len(kept) != len(self.state):
                self.log.debug("state.prune " + kv(removed=len(self.state) - len(kept)))
            self.state = kept

        # prune msg_to_key entries pointing to non-existent keys
        if self.msg_to_key:
            removed = 0
            for mid in list(self.msg_to_key.keys()):
                if self.msg_to_key[mid] not in self.state:
                    del self.msg_to_key[mid]
                    removed += 1
            if removed:
                self.log.debug("state.msgmap.prune " + kv(removed=removed))

        # create today's
        for p in self.cfg.PATIENTS:
            for d in p["doses"]:
                key = DoseKey(p["patient_id"], today, d["time"])
                if key in self.state:
                    continue
                hh, mm = map(int, d["time"].split(":"))
                sched = self._now().replace(hour=hh, minute=mm, second=0, microsecond=0)
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
                self.log.debug(
                    "state.instance.create "
                    + kv(
                        patient_id=inst.patient_id,
                        time=d["time"],
                        text=inst.pill_text,
                        status=inst.status,
                    )
                )

    def _set_status(self, inst: DoseInstance, status: Status, reason: str) -> None:
        """Set status with a consistent debug log."""
        old = inst.status
        inst.status = status.value  # store as string for compatibility
        self.log.debug(
            "state.status.change "
            + kv(
                patient_id=inst.patient_id,
                time=inst.dose_key.time_str,
                from_status=old,
                to_status=inst.status,
                reason=reason,
            )
        )

    def _status(self, inst: DoseInstance) -> Status:
        """Convert stored string status back to enum."""
        s = inst.status
        if s == Status.AWAITING.value:
            return Status.AWAITING
        if s == Status.CONFIRMED.value:
            return Status.CONFIRMED
        if s == Status.ESCALATED.value:
            return Status.ESCALATED
        return Status.PENDING

    # ---- messaging helpers ------------------------------------------------------------
    async def _send_reminder(self, inst: DoseInstance, text_key: str) -> None:
        """
        Send a reminder (first or repeat) with inline confirm (if enabled),
        and remember the message_id → dose mapping for robust callbacks.
        """
        inline_enabled = getattr(self.cfg, "INLINE_CONFIRM_ENABLED", True)
        kb_inline = (
            self.adapter.build_confirm_inline_kb(inst.dose_key)
            if inline_enabled and hasattr(self.adapter, "build_confirm_inline_kb")
            else None
        )
        text = (
            fmt("reminder", pill_text=inst.pill_text)
            if text_key == "reminder"
            else fmt("repeat_reminder")
        )
        msg_id = await self._send_group(inst.group_id, text, reply_markup=kb_inline)
        if msg_id is not None:
            inst.last_message_ids.append(msg_id)
            self.msg_to_key[msg_id] = inst.dose_key
        else:
            self.log.error(
                "msg.reminder.error "
                + kv(
                    group_id=inst.group_id,
                    patient_id=inst.patient_id,
                    time=inst.dose_key.time_str,
                    kind=text_key,
                )
            )

    async def _send_group(
        self, group_id: int, text: str, reply_markup: Any | None = None
    ) -> Optional[int]:
        """
        Wrapper to send a group message with error handling.
        Returns message_id or None on error.

        Compatible with test FakeAdapter that doesn't accept `reply_markup`.
        """
        try:
            self.log.info(
                "msg.engine.reply "
                + kv(
                    group_id=group_id,
                    template=text[:64] + ("..." if len(text) > 64 else ""),
                )
            )
            # Preferred call (adapters that support reply_markup)
            try:
                return await self.adapter.send_group_message(
                    group_id, text, reply_markup=reply_markup
                )
            except TypeError:
                # Fallback: adapter only supports (group_id, text)
                return await self.adapter.send_group_message(group_id, text)
        except Exception as e:
            self.log.error(
                "msg.engine.reply.error " + kv(group_id=group_id, err=str(e))
            )
            return None

    async def _reply(
        self,
        group_id: int,
        template_key: str,
        *,
        with_fixed_kb: Optional[dict] = None,
        **fmt_args: Any,
    ) -> Optional[int]:
        """Send a group message using i18n template; optionally attach fixed reply keyboard."""
        kb = None
        if with_fixed_kb is not None and hasattr(
            self.adapter, "build_patient_reply_kb"
        ):
            try:
                kb = self.adapter.build_patient_reply_kb(with_fixed_kb)
            except Exception as e:
                self.log.debug("kb.build.error " + kv(group_id=group_id, err=str(e)))
        text = fmt(template_key, **fmt_args) if fmt_args else fmt(template_key)
        return await self._send_group(group_id, text, reply_markup=kb)

    async def _prompt(
        self, group_id: int, template_key: str, patient: dict, **fmt_args: Any
    ) -> Optional[int]:
        """Send a ForceReply prompt (selective) for guided input like BP/weight."""
        markup = None
        if hasattr(self.adapter, "build_force_reply"):
            try:
                markup = self.adapter.build_force_reply()
            except Exception as e:
                self.log.debug(
                    "force_reply.build.error " + kv(group_id=group_id, err=str(e))
                )
        text = fmt(template_key, **fmt_args) if fmt_args else fmt(template_key)
        return await self._send_group(group_id, text, reply_markup=markup)

    async def _refresh_reply_kb(self, patient: dict) -> None:
        """
        Refresh fixed reply keyboard using adapter helper, with a safe fallback if missing.
        The adapter method sends a small visible message with the keyboard.
        """
        try:
            if hasattr(self.adapter, "refresh_reply_keyboard") and callable(
                self.adapter.refresh_reply_keyboard
            ):
                await self.adapter.refresh_reply_keyboard(patient)
                return
        except Exception as e:
            self.log.error(
                "keyboard.refresh.error "
                + kv(group_id=patient.get("group_id"), err=str(e))
            )
            # continue to fallback

        # Fallback: send visible message with keyboard directly if we can build it
        try:
            if hasattr(self.adapter, "build_patient_reply_kb"):
                kb = self.adapter.build_patient_reply_kb(patient)
            else:
                kb = None
            await self._send_group(
                patient["group_id"], "Оновив кнопки ↓", reply_markup=kb
            )
        except Exception as e:
            self.log.error(
                "keyboard.refresh.fallback.error "
                + kv(group_id=patient.get("group_id"), err=str(e))
            )

    # ---- tiny sugar -------------------------------------------------------------------
    def _now(self) -> datetime:
        return self.clock.now()

    def _today_str(self) -> str:
        return self.clock.today_str()

    def _dosekey_today(self, patient_id: int, time_str: str) -> DoseKey:
        return DoseKey(patient_id, self._today_str(), time_str)

    # ---- outcome CSV ------------------------------------------------------------------
    def _log_outcome_csv(self, inst: DoseInstance, status: str) -> None:
        """Append a one-line outcome row into the configured CSV (analytics/audit)."""
        line = (
            f"{inst.scheduled_dt_local.strftime('%Y-%m-%d %H:%M')}, "
            f"{inst.patient_id}, {inst.patient_label}, {inst.pill_text}, {status}, {inst.attempts_sent}\n"
        )
        with open(self.cfg.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
