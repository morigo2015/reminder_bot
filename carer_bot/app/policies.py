# app/policies.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, List

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from . import config, prompts, regex_bank
from .regex_bank import (
    LABEL_MEAS_BP,
    LABEL_MEAS_TEMP,
    LABEL_PILL_TAKEN,
    LABEL_PILL_NEGATE,
    LABEL_SYMPTOM,
    classify_text,
    extract_bp,
    extract_temp,
    is_confirmation,
)
from .utils import dbg
from zoneinfo import ZoneInfo

# ------------------------
# In-memory PoC state
# ------------------------

KYIV_TZ = config.TZ  # ZoneInfo("Europe/Kyiv")

@dataclass
class MedState:
    """
    Per (patient, med) runtime state.
    We track the latest scheduled dose time and its confirmation status.
    """
    last_prompt_at: Optional[datetime] = None
    last_confirm_at: Optional[datetime] = None
    nag_count: int = 0
    # For pairing photos and "latest dose wins" logic:
    last_scheduled_due_at: Optional[datetime] = None

@dataclass
class MeasureState:
    """
    Per (patient, measure_kind) runtime state.
    """
    last_prompt_at: Optional[datetime] = None
    last_value: Optional[str] = None  # store a small str like "130/85" or "37.2"
    nag_count: int = 0
    last_scheduled_due_at: Optional[datetime] = None

# patient_id -> (med_id -> MedState)
MED_STATE: Dict[int, Dict[int, MedState]] = {}

# patient_id -> (kind -> MeasureState)
MEASURE_STATE: Dict[int, Dict[str, MeasureState]] = {}

# Unknown intent one-shot clarify flag
CLARIFY_PENDING: Set[int] = set()

# ------------------------
# Helpers
# ------------------------

def _now_local() -> datetime:
    return datetime.now(KYIV_TZ)

def _get_patient_name(patient_id: int) -> str:
    return config.PATIENTS.get(patient_id, {}).get("name", f"Пацієнт {patient_id}")

def _get_patient_tg_id(patient_id: int) -> Optional[int]:
    return config.PATIENTS.get(patient_id, {}).get("tg_user_id")

def _get_med_state(patient_id: int, med_id: int) -> MedState:
    by_med = MED_STATE.setdefault(patient_id, {})
    return by_med.setdefault(med_id, MedState())

def _get_measure_state(patient_id: int, kind: str) -> MeasureState:
    by_kind = MEASURE_STATE.setdefault(patient_id, {})
    return by_kind.setdefault(kind, MeasureState())

def _within_minutes(dt: Optional[datetime], minutes: int) -> bool:
    if not dt:
        return False
    return (_now_local() - dt) <= timedelta(minutes=minutes)

def _format_local(dt: Optional[datetime]) -> str:
    return dt.astimezone(KYIV_TZ).strftime("%Y-%m-%d %H:%M") if dt else "-"

def _nag_deltas() -> List[timedelta]:
    """
    Test hook: when DEBUG_MODE is True, use seconds from DEBUG_NAG_SECONDS,
    otherwise use minutes from NAG_MINUTES.
    """
    if config.DEBUG_MODE and config.DEBUG_NAG_SECONDS:
        return [timedelta(seconds=s) for s in config.DEBUG_NAG_SECONDS]
    return [timedelta(minutes=m) for m in config.NAG_MINUTES]

# ------------------------
# CSV logging (append-only)
# ------------------------

import os, csv
def csv_append(event_kind: str, *, patient_id: int,
               med_id: Optional[int] = None,
               due_time_local: Optional[datetime] = None,
               text: Optional[str] = None,
               systolic: Optional[int] = None,
               diastolic: Optional[int] = None,
               temp_c: Optional[float] = None,
               photo_file_id: Optional[str] = None,
               action: Optional[str] = None,
               nag_count: Optional[int] = None,
               escalated: Optional[bool] = None,
               tg_message_id: Optional[int] = None):
    os.makedirs(config.LOG_DIR, exist_ok=True)
    fname = os.path.join(config.LOG_DIR, f"events_{_now_local().date().isoformat()}.csv")
    new_file = not os.path.exists(fname)
    try:
        with open(fname, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            if new_file:
                w.writerow([
                    "date_time_kyiv","patient_id","event_kind","med_id","due_time_kyiv","text",
                    "systolic","diastolic","temp_c","photo_file_id","action","nag_count","escalated","tg_message_id"
                ])
            w.writerow([
                _format_local(_now_local()), patient_id, event_kind, med_id or "",
                _format_local(due_time_local) if due_time_local else "",
                (text or "").replace("\n"," ").strip(),
                systolic or "", diastolic or "", f"{temp_c:.1f}" if temp_c is not None else "",
                photo_file_id or "", action or "", nag_count if nag_count is not None else "",
                "1" if escalated else "", tg_message_id or ""
            ])
    except Exception as e:
        # Logging must never kill the bot in PoC
        dbg(f"CSV append failed: {e}")

# ------------------------
# Public API (called by main.py handlers / scheduler jobs)
# ------------------------

async def handle_timer_fired(
    bot: Bot,
    scheduler: AsyncIOScheduler,
    *,
    kind: str,                 # "med_due" | "measure_due"
    patient_id: int,
    med_id: Optional[int] = None,
    med_name: Optional[str] = None,
    dose: Optional[str] = None,
    measure_kind: Optional[str] = None,   # "bp" | "temp"
    scheduled_due_at: Optional[datetime] = None,  # defaults to now (Kyiv)
):
    """
    Called by APScheduler jobs: either a med reminder or a measurement reminder.
    Schedules nags (one-off DateTrigger) and enforces dedupe.
    """
    scheduled_due_at = scheduled_due_at or _now_local()
    dbg(f"Timer fired: kind={kind} patient={patient_id} med_id={med_id} measure_kind={measure_kind} due_at={_format_local(scheduled_due_at)}")

    patient_name = _get_patient_name(patient_id)
    chat_id = _get_patient_tg_id(patient_id)
    if chat_id is None:
        dbg(f"Timer skipped: patient {patient_id} has no tg_user_id")
        return

    if kind == "med_due":
        assert med_id is not None, "med_id is required for med_due"
        st = _get_med_state(patient_id, med_id)
        # Dedupe: avoid repeat within DEDUPE_MIN
        if _within_minutes(st.last_prompt_at, config.DEDUPE_MIN):
            dbg(f"Dedupe hit for med_due med_id={med_id}")
            return

        # Send prompt
        text = prompts.med_due(patient_name, med_name or "ліки", dose or "")
        msg = await bot.send_message(chat_id, text)
        st.last_prompt_at = _now_local()
        st.last_scheduled_due_at = scheduled_due_at
        st.last_confirm_at = None
        st.nag_count = 0
        csv_append("prompt_sent", patient_id=patient_id, med_id=med_id,
                   due_time_local=scheduled_due_at, text=text, tg_message_id=msg.message_id)
        dbg(f"Prompt sent for med {med_id}; scheduling nags...")

        # Schedule nags (+30, +90, +24h) or debug seconds
        for idx, delta in enumerate(_nag_deltas(), start=1):
            run_at = scheduled_due_at + delta
            jid = f"nag:med:{patient_id}:{med_id}:{int(scheduled_due_at.timestamp())}:{idx}"
            scheduler.add_job(
                _nag_med_if_unconfirmed,
                trigger=DateTrigger(run_date=run_at),
                id=jid,
                replace_existing=True,
                kwargs=dict(
                    bot=bot, patient_id=patient_id, med_id=med_id,
                    med_name=med_name, scheduled_due_at=scheduled_due_at, nag_index=idx
                ),
            )
            dbg(f"  scheduled nag #{idx} at {_format_local(run_at)} (job_id={jid})")

    elif kind == "measure_due":
        assert measure_kind in {"bp", "temp"}, "measure_kind must be 'bp' or 'temp'"
        st = _get_measure_state(patient_id, measure_kind or "")
        if _within_minutes(st.last_prompt_at, config.DEDUPE_MIN):
            dbg(f"Dedupe hit for measure_due kind={measure_kind}")
            return
        text = prompts.measure_bp_prompt(patient_name) if measure_kind == "bp" else prompts.measure_temp_prompt(patient_name)
        msg = await bot.send_message(chat_id, text)
        st.last_prompt_at = _now_local()
        st.last_scheduled_due_at = scheduled_due_at
        st.nag_count = 0
        st.last_value = None  # reset; expect a fresh value after this due time
        csv_append("prompt_sent", patient_id=patient_id, med_id=None,
                   due_time_local=scheduled_due_at, text=text, tg_message_id=msg.message_id)
        dbg(f"Prompt sent for measure {measure_kind}; scheduling nags...")

        for idx, delta in enumerate(_nag_deltas(), start=1):
            run_at = scheduled_due_at + delta
            jid = f"nag:measure:{patient_id}:{measure_kind}:{int(scheduled_due_at.timestamp())}:{idx}"
            scheduler.add_job(
                _nag_measure_if_missing,
                trigger=DateTrigger(run_date=run_at),
                id=jid,
                replace_existing=True,
                kwargs=dict(
                    bot=bot, patient_id=patient_id, measure_kind=measure_kind,
                    scheduled_due_at=scheduled_due_at, nag_index=idx
                ),
            )
            dbg(f"  scheduled nag #{idx} at {_format_local(run_at)} (job_id={jid})")

async def handle_user_message(
    bot: Bot,
    *,
    patient_id: int,
    text: Optional[str] = None,
    photo_file_id: Optional[str] = None,
):
    """
    Handle patient's text or photo.
    Photo confirmation logic:
      - We consider the *latest* unconfirmed scheduled dose for the patient (the “latest scheduled dose wins” rule).
      - If a photo arrives within PHOTO_CONFIRM_WINDOW around that scheduled time, we treat it as a confirmation.
        Why: this keeps the PoC simple and deterministic when multiple meds exist; a richer final design can
        capture per-med photo replies with explicit buttons or reply-to metadata.
    """
    patient_name = _get_patient_name(patient_id)
    chat_id = _get_patient_tg_id(patient_id)
    if chat_id is None:
        return

    # 1) Photo flow
    if photo_file_id:
        # Find the most recent scheduled dose across meds that isn't confirmed yet.
        latest_pair = None  # (med_id, MedState)
        for mid, st in MED_STATE.get(patient_id, {}).items():
            if st.last_scheduled_due_at:
                if (latest_pair is None) or (st.last_scheduled_due_at > latest_pair[1].last_scheduled_due_at):  # type: ignore[index]
                    latest_pair = (mid, st)
        if latest_pair:
            mid, st = latest_pair
            window_start = st.last_scheduled_due_at + timedelta(minutes=config.PHOTO_CONFIRM_WINDOW[0])
            window_end   = st.last_scheduled_due_at + timedelta(minutes=config.PHOTO_CONFIRM_WINDOW[1])
            now = _now_local()
            dbg(f"Photo received; checking window { _format_local(window_start) } .. { _format_local(window_end) } for med {mid}")
            if window_start <= now <= window_end and not st.last_confirm_at:
                # Confirm medication by photo
                st.last_confirm_at = now
                st.nag_count = 0
                CLARIFY_PENDING.discard(patient_id)
                ack = prompts.med_taken_photo_ack()
                msg = await bot.send_message(chat_id, ack)
                csv_append("med_taken_photo", patient_id=patient_id, med_id=mid,
                           due_time_local=st.last_scheduled_due_at, photo_file_id=photo_file_id,
                           action="confirmed_by_photo", tg_message_id=msg.message_id)
                dbg(f"Photo confirmation accepted for med {mid}")
                return
        # If photo doesn't match any window, just acknowledge politely
        msg = await bot.send_message(chat_id, prompts.ok_ack())
        csv_append("photo_other", patient_id=patient_id, text="<photo>", action="ack", tg_message_id=msg.message_id)
        dbg("Photo outside confirmation window; ack only")
        return

    # 2) Text flow: classify with regex-only PoC classifier
    label = classify_text(text or "")
    dbg(f"Text received; label={label}; text='{(text or '').strip()}'")

    # Clear clarify flag on any meaningful intent
    if label in {LABEL_PILL_TAKEN, LABEL_PILL_NEGATE, LABEL_MEAS_BP, LABEL_MEAS_TEMP, LABEL_SYMPTOM}:
        CLARIFY_PENDING.discard(patient_id)

    # Medication confirmations/negations
    if label == LABEL_PILL_TAKEN or (text and is_confirmation(text)):
        # Pick the latest due med that isn't confirmed yet
        latest_mid, latest_st = None, None
        for mid, st in MED_STATE.get(patient_id, {}).items():
            if st.last_scheduled_due_at and not st.last_confirm_at:
                if (latest_st is None) or (st.last_scheduled_due_at > latest_st.last_scheduled_due_at):  # type: ignore[index]
                    latest_mid, latest_st = mid, st
        if latest_st:
            latest_st.last_confirm_at = _now_local()
            latest_st.nag_count = 0
            msg = await bot.send_message(chat_id, prompts.med_taken_followup())
            csv_append("med_taken_text", patient_id=patient_id, med_id=latest_mid,
                       due_time_local=latest_st.last_scheduled_due_at,
                       text=(text or ""), action="confirmed_by_text", tg_message_id=msg.message_id)
            dbg(f"Confirmation accepted for med {latest_mid} by text")
            return
        # No outstanding dose; just acknowledge
        msg = await bot.send_message(chat_id, prompts.ok_ack())
        csv_append("confirm_no_pending", patient_id=patient_id, text=(text or ""), action="no_pending", tg_message_id=msg.message_id)
        dbg("Confirmation with no pending doses; ack only")
        return

    if label == LABEL_PILL_NEGATE:
        # We do NOT immediately escalate; nags/escalation handled by scheduled nags.
        msg = await bot.send_message(chat_id, prompts.sorry_ack())
        csv_append("pill_negation", patient_id=patient_id, text=(text or ""), action="ack_negation", tg_message_id=msg.message_id)
        dbg("Negation received; keeping nags/escalation policy")
        return

    # Measurements
    if label == LABEL_MEAS_BP:
        sys_dia = extract_bp(text or "")
        if sys_dia:
            sys, dia = sys_dia
            st = _get_measure_state(patient_id, "bp")
            st.last_value = f"{sys}/{dia}"
            csv_append("bp_recorded", patient_id=patient_id, systolic=sys, diastolic=dia, text=(text or ""), action="recorded")
            if sys >= config.HYPERTENSION_SYS or dia >= config.HYPERTENSION_DIA:
                alert = prompts.high_bp_alert(patient_name, sys, dia)
                await bot.send_message(chat_id, alert)
                await bot.send_message(config.CARE_GIVER_CHAT_ID, prompts.caregiver_high_bp(patient_name, sys, dia))
                csv_append("bp_alert", patient_id=patient_id, systolic=sys, diastolic=dia, escalated=True, action="caregiver_notified")
                dbg(f"High BP alert sent and caregiver notified: {sys}/{dia}")
            else:
                await bot.send_message(chat_id, prompts.measure_recorded_ack())
                dbg(f"BP recorded without alert: {sys}/{dia}")
        else:
            await _clarify_or_forward(bot, patient_id, chat_id, patient_name, text or "")
        return

    if label == LABEL_MEAS_TEMP:
        temp = extract_temp(text or "")
        if temp is not None:
            st = _get_measure_state(patient_id, "temp")
            st.last_value = f"{temp:.1f}"
            csv_append("temp_recorded", patient_id=patient_id, temp_c=temp, text=(text or ""), action="recorded")
            if temp >= config.FEVER_C:
                alert = prompts.high_temp_alert(patient_name, temp)
                await bot.send_message(chat_id, alert)
                await bot.send_message(config.CARE_GIVER_CHAT_ID, prompts.caregiver_high_temp(patient_name, temp))
                csv_append("temp_alert", patient_id=patient_id, temp_c=temp, escalated=True, action="caregiver_notified")
                dbg(f"High temperature alert sent and caregiver notified: {temp:.1f}")
            else:
                await bot.send_message(chat_id, prompts.measure_recorded_ack())
                dbg(f"Temperature recorded without alert: {temp:.1f}")
        else:
            await _clarify_or_forward(bot, patient_id, chat_id, patient_name, text or "")
        return

    # Symptom (catch-all)
    if label == LABEL_SYMPTOM:
        csv_append("symptom_reported", patient_id=patient_id, text=(text or ""), action="logged")
        await bot.send_message(chat_id, prompts.ok_ack())
        dbg("Symptom text logged")
        return

    # Unknown → one clarification then forward to caregiver
    await _clarify_or_forward(bot, patient_id, chat_id, patient_name, text or "")
    return

# ------------------------
# Internal: unknown handling & nags
# ------------------------

async def _clarify_or_forward(bot: Bot, patient_id: int, chat_id: int, patient_name: str, last_text: str):
    if patient_id in CLARIFY_PENDING:
        await bot.send_message(config.CARE_GIVER_CHAT_ID, prompts.caregiver_forward_unknown(patient_name, last_text))
        csv_append("forward_unknown", patient_id=patient_id, text=last_text, action="caregiver_forwarded")
        CLARIFY_PENDING.discard(patient_id)
        dbg("Clarify failed; forwarded to caregiver")
    else:
        await bot.send_message(chat_id, prompts.ask_clarify_yes_no())
        csv_append("unknown", patient_id=patient_id, text=last_text, action="clarify_asked")
        CLARIFY_PENDING.add(patient_id)
        dbg("Asked for clarification")

async def _nag_med_if_unconfirmed(
    bot: Bot,
    *,
    patient_id: int,
    med_id: int,
    med_name: Optional[str],
    scheduled_due_at: datetime,
    nag_index: int,
):
    st = _get_med_state(patient_id, med_id)
    chat_id = _get_patient_tg_id(patient_id)
    if chat_id is None:
        return

    # If already confirmed, do nothing
    if st.last_confirm_at and st.last_scheduled_due_at == scheduled_due_at:
        dbg(f"Nag #{nag_index} skipped (already confirmed) for med {med_id}")
        return

    text = prompts.med_reprompt(med_name or "ліки")
    msg = await bot.send_message(chat_id, text)
    st.nag_count = nag_index
    csv_append("nag_sent", patient_id=patient_id, med_id=med_id,
               due_time_local=scheduled_due_at, text=text, nag_count=st.nag_count, tg_message_id=msg.message_id)
    dbg(f"Nag #{nag_index} sent for med {med_id}")

    # After last nag, escalate missed dose
    if nag_index >= len(_nag_deltas()):
        patient_name = _get_patient_name(patient_id)
        due_str = _format_local(scheduled_due_at)
        alert = prompts.med_missed_escalate(patient_name, med_name or "ліки", due_str)
        await bot.send_message(config.CARE_GIVER_CHAT_ID, alert)
        csv_append("missed_dose_escalated", patient_id=patient_id, med_id=med_id,
                   due_time_local=scheduled_due_at, escalated=True, action="caregiver_notified")
        dbg(f"Missed dose escalated for med {med_id}")

async def _nag_measure_if_missing(
    bot: Bot,
    *,
    patient_id: int,
    measure_kind: str,
    scheduled_due_at: datetime,
    nag_index: int,
):
    st = _get_measure_state(patient_id, measure_kind)
    chat_id = _get_patient_tg_id(patient_id)
    if chat_id is None:
        return

    # No strict "confirmation" for measurements; we nag if no value observed since due
    if st.last_scheduled_due_at == scheduled_due_at and st.last_value:
        dbg(f"Nag #{nag_index} for measure {measure_kind} skipped (value present)")
        return

    patient_name = _get_patient_name(patient_id)
    if measure_kind == "bp":
        text = prompts.measure_bp_prompt(patient_name)
    else:
        text = prompts.measure_temp_prompt(patient_name)

    msg = await bot.send_message(chat_id, text)
    st.nag_count = nag_index
    csv_append("nag_sent_measure", patient_id=patient_id,
               due_time_local=scheduled_due_at, text=text, nag_count=st.nag_count, action=f"nag_{measure_kind}", tg_message_id=msg.message_id)
    dbg(f"Nag #{nag_index} sent for measure {measure_kind}")
