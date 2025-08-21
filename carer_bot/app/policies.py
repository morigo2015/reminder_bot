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
from .csvlog import log_med, log_measure
from .events import (
    EV_ACK,
    EV_ACK_NEG,
    EV_CLARIFY_NAG,
    EV_CLARIFY_REQUIRED,
    EV_CONFIRMED,
    EV_DUE,
    EV_ESCALATED,
    EV_NAG,
    EV_BP_RECORDED,
    EV_DUPLICATE_IGNORE,
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


@dataclass
class MeasureState:
    last_measured_on: Optional[date] = None
    clarify_started_at: Optional[datetime] = None


# patient_id -> med_id -> yyyymmdd -> DoseState
MED_STATE: Dict[int, Dict[int, Dict[str, DoseState]]] = {}
# patient_id -> kind -> yyyymmdd -> MeasureState
MEASURE_STATE: Dict[int, Dict[str, Dict[str, MeasureState]]] = {}

BP_WORDS = ("тиск", "систол", "діастол", "пульс", "ат")
_BP_3NUM = re.compile(r"(?P<s>\d{2,3}).*?(?P<d>\d{2,3}).*?(?P<p>\d{2,3})")


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


async def _chat_exists(bot: Bot, chat_id: int) -> bool:
    try:
        await bot.get_chat(chat_id)
        return True
    except TelegramBadRequest as e:
        logger.error("Chat verification failed for chat_id=%s: %s", chat_id, e)
        return False
    except Exception as e:
        logger.exception("Unexpected error verifying chat_id=%s: %s", chat_id, e)
        return False


# ---- Scheduling entrypoints ----
async def schedule_daily_jobs(scheduler: AsyncIOScheduler, bot: Bot) -> None:
    """
    Verify chats and schedule daily pill reminders (CronTrigger) and a single daily BP reminder.
    Patients with invalid group_chat_id are skipped (logged).
    """
    # Verify caregiver user once (direct messages)
    if not await _chat_exists(bot, config.CAREGIVER_USER_ID):
        logger.error(
            "CAREGIVER_USER_ID=%s is invalid or the caregiver hasn't started the bot. "
            "Direct-message escalations will fail until the caregiver starts the bot.",
            config.CAREGIVER_USER_ID,
        )

    for pid, p in config.PATIENTS.items():
        group_id = p.get("group_chat_id")
        if not await _chat_exists(bot, group_id):
            logger.error(
                "Skipping scheduling for patient %s (invalid group_chat_id=%s).",
                pid,
                group_id,
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
    part = prompts.label_daypart(p["labels"]["threshold_hhmm"], st.due_at)
    try:
        msg = await bot.send_message(
            p["group_chat_id"], prompts.med_due(p["name"], part)
        )
        log_med(
            event=EV_DUE,
            patient_id=pid,
            med_id=mid,
            due_at=st.due_at,
            tg_message_id=msg.message_id,
        )
    except TelegramBadRequest as e:
        # Don’t crash future runs; just log once per fire.
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
    try:
        # Direct message to caregiver user
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

    # 1) Pill confirm/negate
    label = classify_text(text)
    if label == LABEL_PILL_NEGATE:
        msg = await bot.send_message(chat_id, prompts.sorry_ack())
        log_med(
            event=EV_ACK_NEG,
            patient_id=pid,
            action="ack_negation",
            text=text,
            tg_message_id=msg.message_id,
        )
        return

    if is_confirmation(text):
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
            if st.confirmed_at:
                msg = await bot.send_message(chat_id, prompts.ok_ack())
                log_med(
                    event=EV_ACK,
                    patient_id=pid,
                    med_id=mid,
                    due_at=st.due_at,
                    action=EV_DUPLICATE_IGNORE,
                    text=text,
                    tg_message_id=msg.message_id,
                )
                return
            st.confirmed_at = now_local()
            _cancel_jobs_for_pill(pid, mid, ymd)
            msg = await bot.send_message(chat_id, prompts.ok_ack())
            log_med(
                event=EV_CONFIRMED,
                patient_id=pid,
                med_id=mid,
                due_at=st.due_at,
                text=text,
                tg_message_id=msg.message_id,
            )
            return
        # no pending today → generic ack
        msg = await bot.send_message(chat_id, prompts.ok_ack())
        log_med(
            event=EV_ACK,
            patient_id=pid,
            action="no_pending",
            text=text,
            tg_message_id=msg.message_id,
        )
        return

    # 2) BP flow (3 numbers or clarify)
    ymd = today_key()
    ms = _get_measure_state(pid, BP_KIND, ymd)
    text_l = (text or "").lower()
    bp_intent = any(w in text_l for w in BP_WORDS) or ms.clarify_started_at is not None
    nums = _BP_3NUM.search(text) if bp_intent else None

    if bp_intent:
        if nums:
            s, d, pval = (
                int(nums.group("s")),
                int(nums.group("d")),
                int(nums.group("p")),
            )
            action = None
            if s < d:
                s, d = d, s
                action = "auto_swapped"
            ms.last_measured_on = now_local().date()
            ms.clarify_started_at = None
            msg = await bot.send_message(chat_id, prompts.bp_recorded_ack(s, d, pval))
            log_measure(
                event=EV_BP_RECORDED,
                patient_id=pid,
                kind=BP_KIND,
                action=action,
                text=f"{s}/{d} {pval}",
                tg_message_id=msg.message_id,
            )
            return
        # enter/continue clarify
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

    # 3) Everything else → simple ack
    msg = await bot.send_message(chat_id, prompts.ok_ack())
    log_measure(
        event=EV_ACK,
        patient_id=pid,
        kind=BP_KIND,
        text=text,
        tg_message_id=msg.message_id,
    )


# ---- Clarify & escalate helpers ----
async def _on_clarify_nag(pid: int, kind: str, ymd: str) -> None:
    ctx = get_ctx()
    bot = ctx.bot
    p = config.PATIENTS[pid]
    ms = _get_measure_state(pid, kind, ymd)
    if ms.clarify_started_at is None:
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
    ctx = get_ctx()
    bot = ctx.bot
    p = config.PATIENTS[pid]
    ms = _get_measure_state(pid, kind, ymd)
    if ms.clarify_started_at is None:
        return
    try:
        # Direct message to caregiver user
        await bot.send_message(
            config.CAREGIVER_USER_ID, prompts.bp_escalate_to_caregiver(p["name"])
        )
        log_measure(
            event=EV_ESCALATED,
            patient_id=pid,
            kind=kind,
            action="bp_missing_or_invalid",
        )
    except TelegramBadRequest as e:
        logger.error(
            "Failed to DM caregiver user_id=%s for BP escalation (pid=%s). "
            "Likely the caregiver hasn't started the bot. Error: %s",
            config.CAREGIVER_USER_ID,
            pid,
            e,
        )
