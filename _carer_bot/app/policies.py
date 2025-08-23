# app/policies.py
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from . import config, prompts
from .csvlog import (
    csv_append,
    log_med,
    log_measure,
    log_pills_detail,
    log_pressure_detail,
)
from .events import (
    SC_OTHER,
    EV_ACK,
    EV_ACK_NEG,
    EV_CLARIFY_NAG,
    EV_CLARIFY_REQUIRED,
    EV_CONFIRMED,
    EV_DUE,
    EV_ESCALATED,
    EV_NAG,
    EV_BP_RECORDED,
    BP_KIND,
)
from .regex_bank import LABEL_PILL_NEGATE, classify_text, is_confirmation
from .utils import now_local, parse_hhmm, today_key
from .ctx import get_ctx

logger = logging.getLogger(__name__)


# ---- In-memory per-day state (MVP) ----
@dataclass
class DoseState:
    due_at: datetime
    confirmed_at: Optional[datetime] = None
    nag_sent_at: Optional[datetime] = None
    escalated: bool = False
    nags: int = 0
    label: str = "?"


@dataclass
class MeasureState:
    last_measured_on: Optional[date] = None
    clarify_started_at: Optional[datetime] = None


# patient_id -> med_id -> yyyymmdd -> DoseState
MED_STATE: Dict[int, Dict[int, Dict[str, DoseState]]] = {}
# patient_id -> kind -> yyyymmdd -> MeasureState
MEASURE_STATE: Dict[int, Dict[str, Dict[str, MeasureState]]] = {}

# Existing BP intent heuristics (kept for clarify flow)
BP_WORDS = ("тиск", "систол", "діастол", "пульс", "ат")
_BP_3NUM = re.compile(r"(?P<s>\d{2,3}).*?(?P<d>\d{2,3}).*?(?P<p>\d{2,3})")
# New strict patterns for typed BP and bare 3 numbers
_TYPE_AND_3NUM_RE = re.compile(
    r"^\s*([^\W\d_]+)\s+(\d{2,3})\s+(\d{2,3})\s+(\d{2,3})(?:\D|$)",
    re.UNICODE,
)
_ONLY_3NUM_RE = re.compile(r"^\s*(\d{2,3})\s+(\d{2,3})\s+(\d{2,3})\s*$")


# ---- Helpers ----
def _get_dose_state(pid: int, mid: int, ymd: str) -> DoseState:
    return (
        MED_STATE.setdefault(pid, {})
        .setdefault(mid, {})
        .setdefault(ymd, DoseState(due_at=now_local()))
    )


def _get_measure_state(pid: int, kind: str, ymd: str) -> MeasureState:
    return (
        MEASURE_STATE.setdefault(pid, {})
        .setdefault(kind, {})
        .setdefault(ymd, MeasureState())
    )


def _pill_nag_delta(pid: int) -> timedelta:
    if config.DEBUG_MODE and config.DEBUG_NAG_SECONDS:
        return timedelta(seconds=config.DEBUG_NAG_SECONDS[0])
    return timedelta(
        minutes=config.cfg(pid, "pill_nag_after_minutes", "pill_nag_after_minutes")
    )


def _clarify_nag_delta(pid: int) -> timedelta:
    if config.DEBUG_MODE and config.DEBUG_NAG_SECONDS:
        return timedelta(seconds=config.DEBUG_NAG_SECONDS[1])
    return timedelta(
        minutes=config.cfg(
            pid, "bp_clarify_nag_after_minutes", "bp_clarify_nag_after_minutes"
        )
    )


def _pill_escalate_after(pid: int) -> timedelta:
    return timedelta(
        minutes=config.cfg(
            pid, "pill_escalate_after_minutes", "pill_escalate_after_minutes"
        )
    )


def _bp_escalate_after(pid: int) -> timedelta:
    return timedelta(
        minutes=config.cfg(
            pid, "bp_escalate_after_minutes", "bp_escalate_after_minutes"
        )
    )


def _cancel_jobs_for_pill(pid: int, mid: int, ymd: str) -> None:
    ctx = get_ctx()
    with suppress(Exception):
        ctx.scheduler.remove_job(config.job_id_med_nag(pid, mid, ymd))
    with suppress(Exception):
        ctx.scheduler.remove_job(config.job_id_med_escalate(pid, mid, ymd))


# ---- Scheduling entrypoints ----
async def schedule_daily_jobs(scheduler: AsyncIOScheduler, bot: Bot) -> None:
    """
    Verify chats and schedule daily pill reminders (CronTrigger) and a single daily BP reminder.
    Patients with invalid group_chat_id are skipped (logged).
    """
    # Verify caregiver user once (direct messages)
    try:
        await bot.get_chat(config.CAREGIVER_USER_ID)
    except TelegramBadRequest as e:
        logger.error(
            "CAREGIVER_USER_ID=%s is invalid or the caregiver hasn't started the bot. "
            "Direct-message escalations will fail until the caregiver starts the bot. Error: %s",
            config.CAREGIVER_USER_ID,
            e,
        )

    for pid, p in config.PATIENTS.items():
        group_id = p.get("group_chat_id")
        try:
            await bot.get_chat(group_id)
        except TelegramBadRequest as e:
            logger.error(
                "Skipping scheduling for patient %s (invalid group_chat_id=%s): %s",
                pid,
                group_id,
                e,
            )
            continue

        # Pills: schedule cron jobs per HH:MM
        for mid, hhmm in enumerate(p.get("pill_times_hhmm", [])):
            hh, mm = parse_hhmm(hhmm)
            scheduler.add_job(
                _on_med_due,
                CronTrigger(hour=hh, minute=mm, timezone=config.TZ),
                id=f"cron_med:{pid}:{mid}",
                args=[pid, mid],
                replace_existing=True,
                misfire_grace_time=60,
            )
            logger.info(
                "Scheduled pill cron pid=%s mid=%s at %02d:%02d", pid, mid, hh, mm
            )

        # BP: once per day (simple default 09:00)
        scheduler.add_job(
            _on_measure_due,
            CronTrigger(hour=9, minute=0, timezone=config.TZ),
            id=f"cron_bp:{pid}",
            args=[pid, BP_KIND],
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled BP cron pid=%s at 09:00", pid)


# ---- Job handlers (fired by scheduler) ----
async def _on_med_due(pid: int, mid: int) -> None:
    ctx = get_ctx()
    bot = ctx.bot
    p = config.PATIENTS[pid]
    ymd = today_key()
    st = _get_dose_state(pid, mid, ymd)
    st.due_at = now_local()
    st.label = prompts.label_daypart(p["labels"]["threshold_hhmm"], st.due_at)
    try:
        msg = await bot.send_message(
            p["group_chat_id"], prompts.med_due(p["name"], st.label)
        )
        log_med(
            event=EV_DUE,
            patient_id=pid,
            med_id=mid,
            due_at=st.due_at,
            tg_message_id=msg.message_id,
        )
    except TelegramBadRequest as e:
        logger.error(
            "Failed to send med_due to group %s (pid=%s mid=%s): %s",
            p["group_chat_id"],
            pid,
            mid,
            e,
        )
        return

    # schedule nag + escalate for *today* only
    nag_at = now_local() + _pill_nag_delta(pid)
    ctx.scheduler.add_job(
        _on_med_nag,
        DateTrigger(run_date=nag_at),
        id=config.job_id_med_nag(pid, mid, ymd),
        args=[pid, mid, ymd],
        replace_existing=True,
    )
    esc_at = st.due_at + _pill_escalate_after(pid)
    ctx.scheduler.add_job(
        _on_med_escalate,
        DateTrigger(run_date=esc_at),
        id=config.job_id_med_escalate(pid, mid, ymd),
        args=[pid, mid, ymd],
        replace_existing=True,
    )


async def _on_med_nag(pid: int, mid: int, ymd: str) -> None:
    ctx = get_ctx()
    bot = ctx.bot
    p = config.PATIENTS[pid]
    st = _get_dose_state(pid, mid, ymd)
    if st.confirmed_at:
        return
    try:
        msg = await bot.send_message(p["group_chat_id"], prompts.med_nag(p["name"]))
        st.nag_sent_at = now_local()
        st.nags += 1
        log_med(
            event=EV_NAG,
            patient_id=pid,
            med_id=mid,
            due_at=st.due_at,
            tg_message_id=msg.message_id,
        )
    except TelegramBadRequest as e:
        logger.error(
            "Failed to send med_nag to group %s (pid=%s mid=%s): %s",
            p["group_chat_id"],
            pid,
            mid,
            e,
        )


async def _on_med_escalate(pid: int, mid: int, ymd: str) -> None:
    ctx = get_ctx()
    bot = ctx.bot
    p = config.PATIENTS[pid]
    st = _get_dose_state(pid, mid, ymd)
    if st.confirmed_at or st.escalated:
        return
    # Notify patient in group first
    try:
        await bot.send_message(
            p["group_chat_id"], prompts.patient_missed_pill_notice(st.label or "")
        )
    except TelegramBadRequest as e:
        logger.error(
            "Failed to send missed pill notice to group %s (pid=%s mid=%s): %s",
            p["group_chat_id"],
            pid,
            mid,
            e,
        )
    # DM caregiver
    try:
        await bot.send_message(
            config.CAREGIVER_USER_ID,
            prompts.med_escalate_to_caregiver(p["name"], st.due_at),
        )
        st.escalated = True
        log_med(
            event=EV_ESCALATED,
            patient_id=pid,
            med_id=mid,
            due_at=st.due_at,
            action="pill_missed",
        )
        # Detail log for pills with result
        log_pills_detail(
            patient_id=pid, label=st.label or "", nags=st.nags, result="ESCALATED"
        )
    except TelegramBadRequest as e:
        logger.error(
            "Failed to DM caregiver user_id=%s for escalation (pid=%s mid=%s). "
            "Likely the caregiver hasn't started the bot. Error: %s",
            config.CAREGIVER_USER_ID,
            pid,
            mid,
            e,
        )


async def _on_measure_due(pid: int, kind: str) -> None:
    ctx = get_ctx()
    bot = ctx.bot
    p = config.PATIENTS[pid]
    try:
        msg = await bot.send_message(
            p["group_chat_id"], prompts.measure_bp_due(p["name"])
        )
        log_measure(
            event=EV_DUE, patient_id=pid, kind=kind, tg_message_id=msg.message_id
        )
    except TelegramBadRequest as e:
        logger.error(
            "Failed to send measure_due to group %s (pid=%s): %s",
            p["group_chat_id"],
            pid,
            e,
        )
    # Clarify nags/escalation are scheduled only if we enter clarify flow.


# ---- User message handling ----
async def handle_patient_text(
    bot: Bot,
    scheduler: AsyncIOScheduler,
    *,
    patient_id: int,
    text: str,
    chat_id: int,
    tg_message_id: int,
) -> None:
    pid = patient_id
    p = config.PATIENTS[pid]
    t = (text or "").strip()

    # 1) Pill confirm/negate
    label = classify_text(t)
    if label == LABEL_PILL_NEGATE:
        msg = await bot.send_message(chat_id, prompts.sorry_ack())
        log_med(
            event=EV_ACK_NEG,
            patient_id=pid,
            action="ack_negation",
            text=t,
            tg_message_id=msg.message_id,
        )
        return

    if is_confirmation(t):
        # confirm latest unconfirmed *today*
        ymd = today_key()
        latest: Optional[Tuple[int, DoseState]] = None
        for mid, by_day in MED_STATE.get(pid, {}).items():
            st = by_day.get(ymd)
            if not st or st.confirmed_at:
                continue
            if latest is None or st.due_at > latest[1].due_at:
                latest = (mid, st)
        if latest:
            mid, st = latest
            # Standard confirmation
            st.confirmed_at = now_local()
            _cancel_jobs_for_pill(pid, mid, ymd)
            # Improved confirmation message with label
            msg = await bot.send_message(
                chat_id, prompts.med_confirmed_with_label(st.label or "")
            )
            log_med(
                event=EV_CONFIRMED,
                patient_id=pid,
                med_id=mid,
                due_at=st.due_at,
                text=t,
                tg_message_id=msg.message_id,
            )
            # Detail pills log
            result_status = (
                "CONFIRMED_AFTER_ESCALATION" if st.escalated else "CONFIRMED"
            )
            log_pills_detail(
                patient_id=pid, label=st.label or "", nags=st.nags, result=result_status
            )
            # If was escalated earlier, politely notify caregiver that it’s resolved
            with suppress(TelegramBadRequest):
                if st.escalated:
                    await bot.send_message(
                        config.CAREGIVER_USER_ID,
                        prompts.caregiver_confirmed_after_escalation(
                            p["name"], st.label or ""
                        ),
                    )
            return
        # no pending today → generic ack
        msg = await bot.send_message(chat_id, prompts.ok_ack())
        log_med(
            event=EV_ACK,
            patient_id=pid,
            action="no_pending",
            text=t,
            tg_message_id=msg.message_id,
        )
        return

    # 2) BP strict typed path FIRST (must start with <letters> then three numbers)
    m = _TYPE_AND_3NUM_RE.match(t)
    if m:
        type_token, s_sys, s_dia, s_pulse = m.groups()
        canon = config.canonicalize_bp_type(type_token)
        if canon:
            s, d, pval = int(s_sys), int(s_dia), int(s_pulse)
            action = None
            if s < d:
                s, d = d, s
                action = "auto_swapped"
            ymd = today_key()
            ms = _get_measure_state(pid, BP_KIND, ymd)
            ms.last_measured_on = now_local().date()
            ms.clarify_started_at = None
            # Ack with TYPE (not daypart)
            msg = await bot.send_message(
                chat_id, prompts.bp_recorded_ack_with_type(canon, s, d, pval)
            )
            log_measure(
                event=EV_BP_RECORDED,
                patient_id=pid,
                kind=BP_KIND,
                action=action,
                text=f"{canon} {s}/{d} {pval}",
                tg_message_id=msg.message_id,
            )
            log_pressure_detail(patient_id=pid, sys=s, dia=d, pulse=pval, type_=canon)
            # cleanup clarify/escalate jobs if any
            with suppress(Exception):
                get_ctx().scheduler.remove_job(config.job_id_bp_clarify(pid, ymd))
            with suppress(Exception):
                get_ctx().scheduler.remove_job(config.job_id_bp_escalate(pid, ymd))
            return
        # leading token present but unknown → ask to retry with correct type
        msg = await bot.send_message(chat_id, prompts.bp_need_type_retry())
        log_measure(
            event=EV_CLARIFY_REQUIRED,
            patient_id=pid,
            kind=BP_KIND,
            action="unknown_bp_type",
            tg_message_id=msg.message_id,
        )
        return

    # If message is exactly three numbers → reject and ask for typed format
    if _ONLY_3NUM_RE.match(t):
        msg = await bot.send_message(chat_id, prompts.bp_need_type_retry())
        log_measure(
            event=EV_CLARIFY_REQUIRED,
            patient_id=pid,
            kind=BP_KIND,
            action="bp_missing_type",
            tg_message_id=msg.message_id,
        )
        return

    # 3) Legacy BP flow gate (keywords/clarify), but DO NOT accept numbers-only here
    ymd = today_key()
    ms = _get_measure_state(pid, BP_KIND, ymd)
    text_l = t.lower()
    bp_intent = any(w in text_l for w in BP_WORDS) or ms.clarify_started_at is not None
    nums = _BP_3NUM.search(t) if bp_intent else None

    if bp_intent:
        if nums:
            # We have numbers under BP intent but no leading type → require typed format
            msg = await bot.send_message(chat_id, prompts.bp_need_type_retry())
            first_time = ms.clarify_started_at is None
            ms.clarify_started_at = ms.clarify_started_at or now_local()
            log_measure(
                event=EV_CLARIFY_REQUIRED,
                patient_id=pid,
                kind=BP_KIND,
                action="bp_missing_type_under_intent",
                tg_message_id=msg.message_id,
            )
            if first_time:
                # schedule clarify nag(s)
                run_at = now_local() + _clarify_nag_delta(pid)
                scheduler.add_job(
                    _on_clarify_nag,
                    DateTrigger(run_date=run_at),
                    id=config.job_id_bp_clarify(pid, ymd),
                    args=[pid, BP_KIND, ymd],
                    replace_existing=True,
                )
                # schedule escalation
                esc_at = ms.clarify_started_at + _bp_escalate_after(pid)
                scheduler.add_job(
                    _on_bp_escalate,
                    DateTrigger(run_date=esc_at),
                    id=config.job_id_bp_escalate(pid, ymd),
                    args=[pid, BP_KIND, ymd],
                    replace_existing=True,
                )
            return

        # enter/continue clarify (no numbers)
        first_time = ms.clarify_started_at is None
        ms.clarify_started_at = now_local()
        msg = await bot.send_message(chat_id, prompts.clarify_bp())
        log_measure(
            event=EV_CLARIFY_REQUIRED,
            patient_id=pid,
            kind=BP_KIND,
            action="missing_numbers",
            tg_message_id=msg.message_id,
        )
        if first_time:
            # schedule clarify nag(s)
            run_at = now_local() + _clarify_nag_delta(pid)
            scheduler.add_job(
                _on_clarify_nag,
                DateTrigger(run_date=run_at),
                id=config.job_id_bp_clarify(pid, ymd),
                args=[pid, BP_KIND, ymd],
                replace_existing=True,
            )
            # schedule escalation
            esc_at = ms.clarify_started_at + _bp_escalate_after(pid)
            scheduler.add_job(
                _on_bp_escalate,
                DateTrigger(run_date=esc_at),
                id=config.job_id_bp_escalate(pid, ymd),
                args=[pid, BP_KIND, ymd],
                replace_existing=True,
            )
        return

    # 4) Everything else → simple ack, but log under SC_OTHER (not 'measure')
    msg = await bot.send_message(chat_id, prompts.ok_ack())
    csv_append(
        scenario=SC_OTHER,
        event=EV_ACK,
        patient_id=pid,
        group_chat_id=p["group_chat_id"],
        text=t,
        tg_message_id=msg.message_id,
    )


# ---- BP clarify follow-ups (ADDED to fix Ruff F821) ----
async def _on_clarify_nag(pid: int, kind: str, ymd: str) -> None:
    """
    Send a clarify nag in the group if clarify is still active and no valid BP was received.
    """
    ctx = get_ctx()
    bot = ctx.bot
    p = config.PATIENTS[pid]
    ms = _get_measure_state(pid, kind, ymd)

    # If measurement was recorded today or clarify not active anymore, skip.
    if ms.last_measured_on == now_local().date() or ms.clarify_started_at is None:
        return

    try:
        msg = await bot.send_message(p["group_chat_id"], prompts.clarify_nag())
        log_measure(
            event=EV_CLARIFY_NAG,
            patient_id=pid,
            kind=kind,
            tg_message_id=msg.message_id,
        )
    except TelegramBadRequest as e:
        logger.error(
            "Failed to send clarify_nag to group %s (pid=%s): %s",
            p["group_chat_id"],
            pid,
            e,
        )


async def _on_bp_escalate(pid: int, kind: str, ymd: str) -> None:
    """
    Escalate BP clarify failure to caregiver via direct message.
    Also cancels pending clarify/escalation jobs for the day.
    """
    ctx = get_ctx()
    bot = ctx.bot
    p = config.PATIENTS[pid]
    ms = _get_measure_state(pid, kind, ymd)

    # If measurement recorded or clarify not active, do nothing.
    if ms.last_measured_on == now_local().date() or ms.clarify_started_at is None:
        return

    try:
        await bot.send_message(
            config.CAREGIVER_USER_ID,
            prompts.bp_escalate_to_caregiver(p["name"]),
        )
        log_measure(
            event=EV_ESCALATED,
            patient_id=pid,
            kind=kind,
            action="bp_clarify_failed",
        )
        # stop clarify for today
        ms.clarify_started_at = None
    except TelegramBadRequest as e:
        logger.error(
            "Failed to DM caregiver user_id=%s for BP escalation (pid=%s). Error: %s",
            config.CAREGIVER_USER_ID,
            pid,
            e,
        )

    # Cleanup any pending jobs for clarity/escalation
    with suppress(Exception):
        ctx.scheduler.remove_job(config.job_id_bp_clarify(pid, ymd))
    with suppress(Exception):
        ctx.scheduler.remove_job(config.job_id_bp_escalate(pid, ymd))
