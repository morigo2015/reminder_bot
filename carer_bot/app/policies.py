# app/policies.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple

import re
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from . import config, prompts
from .csvlog import csv_append
from .events import (
    SC_MED,
    SC_MEASURE,
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
    EV_DUPLICATE_IGNORE,
)
from .regex_bank import LABEL_PILL_NEGATE, classify_text, is_confirmation
from .utils import now_local, parse_hhmm


# ---- In-memory state (PoC) ----
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
    clarify_due_ts: Optional[int] = None  # for job id


# patient_id -> med_id -> DoseState
MED_STATE: Dict[int, Dict[int, DoseState]] = {}
# patient_id -> kind -> MeasureState
MEASURE_STATE: Dict[int, Dict[str, MeasureState]] = {}

BP_WORDS = ("тиск", "систол", "діастол", "пульс", "ат")

_BP_3NUM = re.compile(r"(?P<s>\d{2,3}).*?(?P<d>\d{2,3}).*?(?P<p>\d{2,3})")


# ---- Helpers ----
def _get_dose_state(patient_id: int, med_id: int) -> DoseState:
    by_med = MED_STATE.setdefault(patient_id, {})
    return by_med.setdefault(med_id, DoseState(due_at=now_local()))


def _get_measure_state(patient_id: int, kind: str) -> MeasureState:
    by_kind = MEASURE_STATE.setdefault(patient_id, {})
    return by_kind.setdefault(kind, MeasureState())


def _within_minutes(dt: Optional[datetime], minutes: int) -> bool:
    if not dt:
        return False
    return (now_local() - dt) <= timedelta(minutes=minutes)


def _pill_nag_delta(patient_id: int) -> timedelta:
    if config.DEBUG_MODE and config.DEBUG_NAG_SECONDS:
        return timedelta(seconds=config.DEBUG_NAG_SECONDS[0])
    minutes = config.PATIENTS[patient_id].get(
        "pill_nag_after_minutes", config.DEFAULTS["pill_nag_after_minutes"]
    )
    return timedelta(minutes=minutes)


def _clarify_nag_delta(patient_id: int) -> timedelta:
    if config.DEBUG_MODE and config.DEBUG_NAG_SECONDS:
        return timedelta(seconds=config.DEBUG_NAG_SECONDS[1])
    minutes = config.PATIENTS[patient_id].get(
        "bp_clarify_nag_after_minutes", config.DEFAULTS["bp_clarify_nag_after_minutes"]
    )
    return timedelta(minutes=minutes)


def _pill_escalate_after(patient_id: int) -> timedelta:
    minutes = config.PATIENTS[patient_id].get(
        "pill_escalate_after_minutes", config.DEFAULTS["pill_escalate_after_minutes"]
    )
    return timedelta(minutes=minutes)


def _bp_escalate_after(patient_id: int) -> timedelta:
    minutes = config.PATIENTS[patient_id].get(
        "bp_escalate_after_minutes", config.DEFAULTS["bp_escalate_after_minutes"]
    )
    return timedelta(minutes=minutes)


# ---- Scheduling entrypoints ----
async def schedule_daily_jobs(scheduler: AsyncIOScheduler) -> None:
    """
    Schedules pill reminders for each patient (med_id is ordinal in pill_times_hhmm),
    and a single "bp measure" daily reminder job (no nags for due, only clarify nags).
    """
    for pid, cfg in config.PATIENTS.items():
        # Pills
        for mid, hhmm in enumerate(cfg.get("pill_times_hhmm", [])):
            hh, mm = parse_hhmm(hhmm)
            # schedule next run "today" or "tomorrow" if already passed
            due = now_local().replace(hour=hh, minute=mm, second=0, microsecond=0)
            if due < now_local():
                due += timedelta(days=1)
            MED_STATE.setdefault(pid, {})[mid] = DoseState(due_at=due)
            scheduler.add_job(
                _on_med_due,
                DateTrigger(run_date=due),
                id=config.job_id_for_med(pid, mid),
                args=[pid, mid],
                replace_existing=True,
                misfire_grace_time=60,
            )
        # BP (one per day)
        hh, mm = (9, 0)  # simple MVP default time
        due = now_local().replace(hour=hh, minute=mm, second=0, microsecond=0)
        if due < now_local():
            due += timedelta(days=1)
        scheduler.add_job(
            _on_measure_due,
            DateTrigger(run_date=due),
            id=config.job_id_for_measure(pid, "bp"),
            args=[pid, "bp"],
            replace_existing=True,
            misfire_grace_time=60,
        )


# ---- Job handlers ----
async def _on_med_due(patient_id: int, med_id: int) -> None:
    from .main import BOT  # lazy to avoid cycle

    cfg = config.PATIENTS[patient_id]
    state = _get_dose_state(patient_id, med_id)
    state.due_at = now_local()
    # send
    part = prompts.label_daypart(cfg["labels"]["threshold_hhmm"], state.due_at)
    msg = await BOT.send_message(
        cfg["group_chat_id"], prompts.med_due(cfg["name"], part)
    )
    csv_append(
        scenario=SC_MED,
        event=EV_DUE,
        patient_id=patient_id,
        group_chat_id=cfg["group_chat_id"],
        med_id=med_id,
        due_at=state.due_at,
        tg_message_id=msg.message_id,
    )
    # schedule nag
    nag_at = now_local() + _pill_nag_delta(patient_id)
    scheduler: AsyncIOScheduler = BOT["scheduler"]  # attached in main
    scheduler.add_job(
        _on_med_nag,
        DateTrigger(run_date=nag_at),
        id=config.job_id_for_clarify(
            patient_id, f"pill{med_id}", int(state.due_at.timestamp())
        ),
        args=[patient_id, med_id, int(state.due_at.timestamp())],
        replace_existing=True,
    )


async def _on_med_nag(patient_id: int, med_id: int, due_ts: int) -> None:
    from .main import BOT

    cfg = config.PATIENTS[patient_id]
    state = _get_dose_state(patient_id, med_id)
    # if already confirmed, noop
    if state.confirmed_at:
        return
    msg = await BOT.send_message(cfg["group_chat_id"], prompts.med_nag(cfg["name"]))
    state.nag_sent_at = now_local()
    csv_append(
        scenario=SC_MED,
        event=EV_NAG,
        patient_id=patient_id,
        group_chat_id=cfg["group_chat_id"],
        med_id=med_id,
        due_at=state.due_at,
        tg_message_id=msg.message_id,
    )
    # schedule escalation check
    esc_at = state.due_at + _pill_escalate_after(patient_id)
    scheduler: AsyncIOScheduler = BOT["scheduler"]
    scheduler.add_job(
        _on_escalate_missed_pill,
        DateTrigger(run_date=esc_at),
        id=config.job_id_for_escalate(patient_id, f"pill{med_id}", due_ts),
        args=[patient_id, med_id, due_ts],
        replace_existing=True,
    )


async def _on_escalate_missed_pill(patient_id: int, med_id: int, due_ts: int) -> None:
    from .main import BOT

    cfg = config.PATIENTS[patient_id]
    state = _get_dose_state(patient_id, med_id)
    if state.confirmed_at or state.escalated:
        return
    await BOT.send_message(
        config.CAREGIVER_CHAT_ID,
        prompts.med_escalate_to_caregiver(cfg["name"], state.due_at),
    )
    state.escalated = True
    csv_append(
        scenario=SC_MED,
        event=EV_ESCALATED,
        patient_id=patient_id,
        group_chat_id=cfg["group_chat_id"],
        med_id=med_id,
        due_at=state.due_at,
        action="pill_missed",
    )


async def _on_measure_due(patient_id: int, kind: str) -> None:
    from .main import BOT

    cfg = config.PATIENTS[patient_id]
    msg = await BOT.send_message(
        cfg["group_chat_id"], prompts.measure_bp_due(cfg["name"])
    )
    csv_append(
        scenario=SC_MEASURE,
        event=EV_DUE,
        patient_id=patient_id,
        group_chat_id=cfg["group_chat_id"],
        kind=kind,
        tg_message_id=msg.message_id,
    )
    # Note: no nag for "due". Clarify nags happen only if we entered clarify flow.


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
    """
    Unified patient text handler:
      - Pill confirm or negate
      - BP data, or clarify loop
      - Otherwise: simple ack + CSV
    """
    cfg = config.PATIENTS[patient_id]
    # 1) Pill confirm/negate handling (very lightweight, last unconfirmed dose wins)
    label = classify_text(text)
    if label == LABEL_PILL_NEGATE:
        msg = await bot.send_message(chat_id, prompts.sorry_ack())
        csv_append(
            scenario=SC_MED,
            event=EV_ACK_NEG,
            patient_id=patient_id,
            group_chat_id=cfg["group_chat_id"],
            action="ack_negation",
            text=text,
            tg_message_id=msg.message_id,
        )
        return

    if is_confirmation(text):
        # confirm latest unconfirmed dose within escalate window
        latest_unconfirmed: Optional[Tuple[int, DoseState]] = None
        for mid, st in MED_STATE.get(patient_id, {}).items():
            if st.confirmed_at:
                continue
            if latest_unconfirmed is None or st.due_at > latest_unconfirmed[1].due_at:
                latest_unconfirmed = (mid, st)
        if latest_unconfirmed:
            mid, st = latest_unconfirmed
            # idempotency: if already confirmed recently (race), mark duplicate
            if st.confirmed_at and _within_minutes(st.confirmed_at, 120):
                msg = await bot.send_message(chat_id, prompts.ok_ack())
                csv_append(
                    scenario=SC_MED,
                    event=EV_ACK,
                    patient_id=patient_id,
                    group_chat_id=cfg["group_chat_id"],
                    med_id=mid,
                    due_at=st.due_at,
                    action=EV_DUPLICATE_IGNORE,
                    text=text,
                    tg_message_id=msg.message_id,
                )
                return
            st.confirmed_at = now_local()
            msg = await bot.send_message(chat_id, prompts.ok_ack())
            csv_append(
                scenario=SC_MED,
                event=EV_CONFIRMED,
                patient_id=patient_id,
                group_chat_id=cfg["group_chat_id"],
                med_id=mid,
                due_at=st.due_at,
                text=text,
                tg_message_id=msg.message_id,
            )
            return
        # no pending dose, but confirmation arrived → treat as generic ack
        msg = await bot.send_message(chat_id, prompts.ok_ack())
        csv_append(
            scenario=SC_OTHER,
            event=EV_ACK,
            patient_id=patient_id,
            group_chat_id=cfg["group_chat_id"],
            action="no_pending",
            text=text,
            tg_message_id=msg.message_id,
        )
        return

    # 2) BP attempt or clarify path
    ms = _get_measure_state(patient_id, "bp")
    text_l = text.lower()
    bp_intent = any(w in text_l for w in BP_WORDS) or ms.clarify_started_at is not None
    nums = _BP_3NUM.search(text) if bp_intent else None

    if bp_intent:
        if nums:
            s, d, p = int(nums.group("s")), int(nums.group("d")), int(nums.group("p"))
            ms.last_measured_on = now_local().date()
            ms.clarify_started_at = None
            ms.clarify_due_ts = None
            msg = await bot.send_message(chat_id, prompts.bp_recorded_ack(s, d, p))
            csv_append(
                scenario=SC_MEASURE,
                event=EV_BP_RECORDED,
                patient_id=patient_id,
                group_chat_id=cfg["group_chat_id"],
                kind="bp",
                text=f"{s}/{d} {p}",
                tg_message_id=msg.message_id,
            )
            return
        # enter or continue clarify
        first_time = ms.clarify_started_at is None
        ms.clarify_started_at = now_local()
        msg = await bot.send_message(chat_id, prompts.clarify_bp())
        csv_append(
            scenario=SC_MEASURE,
            event=EV_CLARIFY_REQUIRED,
            patient_id=patient_id,
            group_chat_id=cfg["group_chat_id"],
            kind="bp",
            action="missing_numbers",
            tg_message_id=msg.message_id,
        )
        if first_time:
            # schedule clarify nag(s)
            run_at = now_local() + _clarify_nag_delta(patient_id)
            scheduler.add_job(
                _on_clarify_nag,
                DateTrigger(run_date=run_at),
                id=config.job_id_for_clarify(
                    patient_id, "bp", int(ms.clarify_started_at.timestamp())
                ),
                args=[patient_id, "bp", int(ms.clarify_started_at.timestamp())],
                replace_existing=True,
            )
            # schedule escalation
            esc_at = ms.clarify_started_at + _bp_escalate_after(patient_id)
            scheduler.add_job(
                _on_bp_escalate,
                DateTrigger(run_date=esc_at),
                id=config.job_id_for_escalate(
                    patient_id, "bp", int(ms.clarify_started_at.timestamp())
                ),
                args=[patient_id, "bp", int(ms.clarify_started_at.timestamp())],
                replace_existing=True,
            )
        return

    # 3) Everything else → simple ack
    msg = await bot.send_message(chat_id, prompts.ok_ack())
    csv_append(
        scenario=SC_OTHER,
        event=EV_ACK,
        patient_id=patient_id,
        group_chat_id=cfg["group_chat_id"],
        text=text,
        tg_message_id=msg.message_id,
    )


# ---- Clarify & escalate helpers ----
async def _on_clarify_nag(patient_id: int, kind: str, due_ts: int) -> None:
    from .main import BOT

    cfg = config.PATIENTS[patient_id]
    ms = _get_measure_state(patient_id, kind)
    if ms.clarify_started_at is None:
        return
    # still unresolved → nag
    msg = await BOT.send_message(cfg["group_chat_id"], prompts.clarify_nag())
    csv_append(
        scenario=SC_MEASURE,
        event=EV_CLARIFY_NAG,
        patient_id=patient_id,
        group_chat_id=cfg["group_chat_id"],
        kind=kind,
        tg_message_id=msg.message_id,
    )


async def _on_bp_escalate(patient_id: int, kind: str, due_ts: int) -> None:
    from .main import BOT

    cfg = config.PATIENTS[patient_id]
    ms = _get_measure_state(patient_id, kind)
    if ms.clarify_started_at is None:
        return
    await BOT.send_message(
        config.CAREGIVER_CHAT_ID, prompts.bp_escalate_to_caregiver(cfg["name"])
    )
    csv_append(
        scenario=SC_MEASURE,
        event=EV_ESCALATED,
        patient_id=patient_id,
        group_chat_id=cfg["group_chat_id"],
        kind=kind,
        action="bp_missing_or_invalid",
    )
    # keep clarify open; caregiver notified
